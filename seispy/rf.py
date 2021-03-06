#!/usr/bin/env python

import obspy
from obspy.io.sac import SACTrace
import re
from seispy.io import wsfetch
from os.path import join
from seispy.para import para
import seispy
from seispy.eq import eq
from seispy.setuplog import setuplog
import glob
import numpy as np
from datetime import timedelta
import pandas as pd
from obspy.taup import TauPyModel
import configparser
import argparse
import sys
import matplotlib.pyplot as plt


def datestr2regex(datestr):
    pattern = datestr.replace('%Y', r'\d{4}')
    pattern = pattern.replace('%m', r'\d{2}')
    pattern = pattern.replace('%d', r'\d{2}')
    pattern = pattern.replace('%j', r'\d{3}')
    pattern = pattern.replace('%H', r'\d{2}')
    pattern = pattern.replace('%M', r'\d{2}')
    pattern = pattern.replace('%S', r'\d{2}')
    return pattern


def read_catalog(logpath, b_time, e_time, stla, stlo, magmin=5.5, magmax=10, dismin=30, dismax=90):
    col = ['date', 'evla', 'evlo', 'evdp', 'mag']
    eq_lst = pd.DataFrame(columns=col)
    with open(logpath) as f:
        lines = f.readlines()
        for line in lines:
            line_sp = line.strip().split()
            date_now = obspy.UTCDateTime.strptime('.'.join(line_sp[0:3]) + 'T' + '.'.join(line_sp[4:7]),
                                                  '%Y.%m.%dT%H.%M.%S')
            evla = float(line_sp[7])
            evlo = float(line_sp[8])
            evdp = float(line_sp[9])
            mw = float(line_sp[10])
            dis = seispy.distaz(stla, stlo, evla, evlo).delta
            # bazi = seispy.distaz(stla, stlo, evla, evlo).getBaz()
            if b_time <= date_now <= e_time and magmin <= mw <= magmax and dismin <= dis <= dismax:
                this_data = pd.DataFrame([[date_now, evla, evlo, evdp, mw]], columns=col)
                eq_lst = eq_lst.append(this_data, ignore_index=True)
    return eq_lst


def load_station_info(pathname, ref_comp, suffix):
    try:
        ex_sac = glob.glob(join(pathname, '*{0}*{1}'.format(ref_comp, suffix)))[0]
    except Exception:
        raise FileNotFoundError('no such SAC file in {0}'.format(pathname))
    ex_tr = SACTrace.read(ex_sac, headonly=True)
    return ex_tr.knetwk, ex_tr.kstnm, ex_tr.stla, ex_tr.stlo, ex_tr.stel


def match_eq(eq_lst, pathname, stla, stlo, ref_comp='Z', suffix='SAC', offset=None,
             tolerance=210, dateformat='%Y.%j.%H.%M.%S', switchEN=False, reverseE=False, reverseN=False):
    pattern = datestr2regex(dateformat)
    ref_eqs = glob.glob(join(pathname, '*{0}*{1}'.format(ref_comp, suffix)))
    sac_files = []
    for ref_sac in ref_eqs:
        try:
            datestr = re.findall(pattern, ref_sac)[0]
        except IndexError:
            raise IndexError('Error data format in {}'.format(ref_sac))
        if isinstance(offset, (int, float)):
            sac_files.append([datestr, obspy.UTCDateTime.strptime(datestr, dateformat), -offset])
        elif offset is None:
            try:
                tr = obspy.read(ref_sac)[0]
            except TypeError:
                continue
            sac_files.append([datestr, tr.stats.starttime, tr.stats.sac.o])
        else:
            raise TypeError('offset should be int or float type')
    new_col = ['dis', 'bazi', 'data']
    eq_match = pd.DataFrame(columns=new_col)
    for datestr, b_time, offs in sac_files:
        date_range_begin = b_time + timedelta(seconds=offs - tolerance)
        date_range_end = b_time + timedelta(seconds=offs + tolerance)
        results = eq_lst[(eq_lst.date > date_range_begin) & (eq_lst.date < date_range_end)]
        if len(results) != 1:
            continue
        try:
            this_eq = eq(pathname, datestr, suffix, switchEN=switchEN, reverseE=reverseE, reverseN=reverseN)
        except Exception as e:
            continue
        this_eq.get_time_offset(results.iloc[0]['date'])
        daz = seispy.distaz(stla, stlo, results.iloc[0]['evla'], results.iloc[0]['evlo'])
        this_df = pd.DataFrame([[daz.delta, daz.baz, this_eq]], columns=new_col, index=results.index.values)
        eq_match = eq_match.append(this_df)
    ind = eq_match.index.drop_duplicates(False)
    eq_match = eq_match.loc[ind]
    return pd.concat([eq_lst, eq_match], axis=1, join='inner')


class stainfo():
    def __init__(self):
        self.network = ''
        self.station = ''
        self.stla = 0.
        self.stlo = 0.
        self.stel = 0.

    def get_stainfo(self):
        return self.__dict__

    def load_stainfo(self, pathname, ref_comp, suffix):
        (self.network, self.station, self.stla, self.stlo, self.stel) = load_station_info(pathname, ref_comp, suffix)


def CfgParser(cfg_file):
    cf = configparser.RawConfigParser()
    pa = para()
    try:
        cf.read(cfg_file)
    except Exception:
        raise FileNotFoundError('Cannot open configure file %s' % cfg_file)
    pa.datapath = cf.get('path', 'datapath')
    pa.rfpath = cf.get('path', 'rfpath')
    pa.imagepath = cf.get('path', 'imagepath')
    logpath = cf.get('path', 'catalogpath')
    if logpath != '':
        pa.catalogpath = cf.get('path', 'catalogpath')
    sections = cf.sections()
    sections.remove('path')
    for sec in sections:
        for key, value in cf.items(sec):
            if key == 'date_begin':
                pa.__dict__[key] = obspy.UTCDateTime(value)
            elif key == 'date_end':
                pa.__dict__[key] = obspy.UTCDateTime(value)
            elif key == 'offset':
                try:
                    pa.__dict__[key] = float(value)
                except:
                    pa.__dict__[key] = None
            elif key == 'itmax':
                pa.__dict__[key] = int(value)
            elif key == 'only_r':
                pa.__dict__[key] = cf.getboolean(sec, 'only_r')
            elif key == 'criterion':
                pa.criterion = value
            else:
                try:
                    pa.__dict__[key] = float(value)
                except ValueError:
                    pa.__dict__[key] = value
    return pa


def CfgModify(cfg_file, session, key, value):
    cf = configparser.RawConfigParser()
    try:
        cf.read(cfg_file)
    except Exception:
        raise FileNotFoundError('Cannot open configure file %s' % cfg_file)
    cf.set(session, key, value)
    cf.write(open(cfg_file, 'w'))


def _plotampt(x, y, ampt, shift_all):
    xx, yy = np.meshgrid(x, y)
    f = plt.figure(figsize=(8, 8))
    plt.pcolor(xx, yy, ampt)
    plt.scatter(shift_all, y)
    return f


class RF(object):
    def __init__(self, cfg_file=None, log=None):
        if cfg_file is None:
            self.para = para()
        elif isinstance(cfg_file, str):
            self.para = CfgParser(cfg_file)
        else:
            raise TypeError('cfg should be \'str\' not \'{0}\''.format(type(cfg_file)))
        if not isinstance(self.para, para):
            raise TypeError('Input value should be class seispy.rf.para')
        if log is None:
            self.logger = setuplog()
        else:
            self.logger = log
        self.eq_lst = pd.DataFrame()
        self.eqs = pd.DataFrame()
        self.model = TauPyModel('iasp91')
        self.stainfo = stainfo()

    @property
    def date_begin(self):
        return self.para.date_begin

    @date_begin.setter
    def date_begin(self, value):
        self.para.date_begin = value

    @property
    def date_end(self):
        return self.para.date_end

    @date_end.setter
    def date_end(self, value):
        self.para.date_end = value

    def load_stainfo(self):
        try:
            self.logger.RFlog.info('Load station info from {0}'.format(self.para.datapath))
            self.stainfo.load_stainfo(self.para.datapath, self.para.ref_comp, self.para.suffix)
        except Exception as e:
            self.logger.RFlog.error('{0}'.format(e))
            raise e

    def search_eq(self, local=False, server=None, catalog='GCMT'):
        if not local:
            try:
                if server is None:
                    server = self.para.catalog_server
                self.logger.RFlog.info('Searching earthquakes from {}'.format(server))
                self.eq_lst = wsfetch(server, starttime=self.para.date_begin, endtime=self.para.date_end,
                                      latitude=self.stainfo.stla, longitude=self.stainfo.stlo,
                                      minmagnitude=self.para.magmin, maxmagnitude=self.para.magmax,
                                      minradius=self.para.dismin, maxradius=self.para.dismax, catalog=catalog)
            except Exception as e:
                raise ConnectionError(e)
        else:
            try:
                self.logger.RFlog.info(
                    'Searching earthquakes from {0} to {1}'.format(self.date_begin.strftime('%Y.%m.%dT%H:%M:%S'),
                                                                   self.date_end.strftime('%Y.%m.%dT%H:%M:%S')))
                self.eq_lst = read_catalog(self.para.catalogpath, self.para.date_begin, self.para.date_end,
                                           self.stainfo.stla, self.stainfo.stlo,
                                           magmin=self.para.magmin, magmax=self.para.magmax,
                                           dismin=self.para.dismin, dismax=self.para.dismax)
            except Exception as e:
                self.logger.RFlog.error('{0}'.format(e))
                raise e

    def match_eq(self, switchEN=False, reverseE=False, reverseN=False):
        try:
            self.logger.RFlog.info('Match SAC files')
            self.eqs = match_eq(self.eq_lst, self.para.datapath, self.stainfo.stla, self.stainfo.stlo,
                                ref_comp=self.para.ref_comp, suffix=self.para.suffix,
                                offset=self.para.offset, tolerance=self.para.tolerance,
                                dateformat=self.para.dateformat, switchEN=switchEN, reverseE=reverseE, reverseN=reverseN)
        except Exception as e:
            self.logger.RFlog.error('{0}'.format(e))
            raise e
        self.logger.RFlog.info('{0} earthquakes matched'.format(self.eqs.shape[0]))
        
    '''
    def save(self, path=''):
        if path == '':
            path = '{0}.{1}.h5'.format(self.stainfo.network, self.stainfo.station)

        d = {'para': self.para.__dict__, 'stainfo': self.stainfo.__dict__, 'eq_lst': self.eq_lst, 'eqs': self.eqs}
        try:
            self.logger.RFlog.info('Saving project to {0}'.format(path))
            dd.io.save(path, d)
        except PerformanceWarning:
            pass
        except Exception as e:
            self.logger.RFlog.error('{0}'.format(e))
            raise IOError(e)

    def load(self, path):
        try:
            self.logger.RFlog.info('Loading {0}'.format(path))
            fdd = dd.io.load(path)
        except Exception as e:
            self.logger.RFlog.error('{0}'.format(e))
            raise IOError('Cannot read {0}'.format(path))

        try:
            self.para.__dict__.update(fdd['para'])
            self.stainfo.__dict__.update(fdd['stainfo'])
            self.eq_lst = fdd['eq_lst']
            self.eqs = fdd['eqs']
        except Exception as e:
            raise ValueError(e)
    '''
    
    def detrend(self):
        self.logger.RFlog.info('Detrend all data')
        for _, row in self.eqs.iterrows():
            row['data'].detrend()

    def filter(self, freqmin=None, freqmax=None, order=4):
        if freqmin is None:
            freqmin = self.para.freqmin
        if freqmax is None:
            freqmax = self.para.freqmax
        self.logger.RFlog.info('Filter all data from {0} to {1}'.format(freqmin, freqmax))
        for _, row in self.eqs.iterrows():
            row['data'].filter(freqmin=freqmin, freqmax=freqmax, order=order)

    def cal_phase(self):
        self.logger.RFlog.info('Calculate arrivals and ray parameters for all data')
        for _, row in self.eqs.iterrows():
            row['data'].get_arrival(self.model, row['evdp'], row['dis'])
            # row['data'].get_raypara(self.model, row['evdp'], row['dis'])

    def baz_correct(self, time_b=10, time_e=20, offset=90):
        self.logger.RFlog.info('correct back-azimuth')
        y = np.arange(self.eqs.shape[0])
        shift_all = np.array([])
        x = np.arange(-offset, offset)
        ampt_all = np.empty([0, x.shape[0]])
        for i, row in self.eqs.iterrows():
            curr_baz, ampt = row['data'].search_baz(row['bazi'], time_b=time_b, time_e=time_e, offset=offset)
            shift_all = np.append(shift_all, curr_baz)
            ampt_all = np.vstack((ampt_all, ampt))
        if None in shift_all:
            self.logger.RFlog.error('Range of searching bazi is too small.')
            sys.exit(1)
        baz_shift = np.mean(shift_all[np.where(np.logical_not(np.isnan(shift_all)))])
        # fig = _plotampt(x, y, ampt_all, shift_all)
        # fig.savefig('{}_rotation.png'.format(self.stainfo.station))
        # self._baz_confirm(offset, ampt_all)
        self.logger.RFlog.info('Average {:.1f} deg offset in back-azimuth'.format(baz_shift))
        self.eqs['bazi'] = np.mod(self.eqs['bazi'] + baz_shift, 360)

    # def _baz_confirm(self, offset, ampt_all):
    #     y = np.arange(self.eqs.shape[0])
    #     x = np.linspace(-offset, offset, ampt_all.shape[1])
    #     fig = _plotampt(x, y, ampt_all)
    #     if messagebox.askyesno('Back-azimuth correction',
    #                            'Would you like to keep this correction?'):
    #         fig.close()
    #     else:
    #         self.logger.RFlog.error('Manual interruption.')
    #         fig.close()
    #         sys.exit(1)

    def rotate(self, method='NE->RT'):
        self.logger.RFlog.info('Rotate {0} phase {1}'.format(self.para.phase, method))
        drop_idx = []
        for i, row in self.eqs.iterrows():
            try:
                row['data'].rotate(row['bazi'], method=method, phase=self.para.phase)
            except Exception as e:
                self.logger.RFlog.error('{}: {}'.format(row['data'].datestr, e))
                drop_idx.append(i)
        self.eqs.drop(drop_idx, inplace=True)

    def drop_eq_snr(self, length=None):
        if length is None:
            length = self.para.noiselen
        self.logger.RFlog.info('Reject data record with SNR less than {0}'.format(self.para.noisegate))
        drop_lst = []
        for i, row in self.eqs.iterrows():
            snr_E, snr_N, snr_Z = row['data'].snr(length=length)
            if (np.nan in (snr_E, snr_N, snr_Z) or snr_E < self.para.noisegate
               or snr_N < self.para.noisegate or snr_Z < self.para.noisegate):
                drop_lst.append(i)
        self.eqs.drop(drop_lst, inplace=True)
        self.logger.RFlog.info('{0} events left after SNR calculation'.format(self.eqs.shape[0]))

    def trim(self):
        for _, row in self.eqs.iterrows():
            row['data'].trim(self.para.time_before, self.para.time_after, self.para.phase)

    def deconv(self, itmax=None, minderr=None):
        if itmax is None:
            itmax = self.para.itmax
        if minderr is None:
            minderr = self.para.minderr
        if self.para.phase == 'P':
            shift = self.para.time_before
        elif self.para.phase == 'S':
            shift = self.para.time_after
        else:
            pass
        drop_lst = []

        count = 0
        for i, row in self.eqs.iterrows():
            count += 1
            try:
                row['data'].deconvolute(shift, self.para.time_after, self.para.gauss, phase=self.para.phase,
                                    only_r=self.para.only_r, itmax=itmax, minderr=minderr, target_dt=self.para.target_dt)
                self.logger.RFlog.info('Iterative Decon {0} ({3}/{4}) iterations: {1}; final RMS: {2:.4f}'.format(
                    row['data'].datestr, row['data'].it, row['data'].rms[-1], count, self.eqs.shape[0]))
            except Exception as e:
                self.logger.RFlog.error('{}: {}'.format(row['data'].datestr, e))
                drop_lst.append(i)
        self.eqs.drop(drop_lst, inplace=True)

    def saverf(self):
        if self.para.phase == 'P':
            shift = self.para.time_before
            npts = int((self.para.time_before + self.para.time_after)/self.para.target_dt+1)
            criterion = self.para.criterion
        elif self.para.phase == 'S':
            shift = self.para.time_after
            criterion = None
        else:
            pass
        good_lst = []

        self.logger.RFlog.info('Save RFs with criterion of {}'.format(criterion))
        for i, row in self.eqs.iterrows():
            if row['data'].judge_rf(shift, npts, criterion=criterion):
                row['data'].saverf(self.para.rfpath, evtstr=row['date'].strftime('%Y.%j.%H.%M.%S'), phase=self.para.phase, shift=shift,
                                   evla=row['evla'], evlo=row['evlo'], evdp=row['evdp'], baz=row['bazi'],
                                   mag=row['mag'], gcarc=row['dis'], gauss=self.para.gauss, only_r=self.para.only_r)
                good_lst.append(i)
        self.logger.RFlog.info('{} PRFs are saved.'.format(len(good_lst)))
        self.eqs = self.eqs.loc[good_lst]


def prf():
    parser = argparse.ArgumentParser(description="Calculating RFs for single station")
    parser.add_argument('cfg_file', type=str, help='Path to RF configure file')
    parser.add_argument('-l', help="use local catalog. Default is false", dest='islocal', action='store_true')
    parser.add_argument('-r', help='Reverse components: EN, E or N', dest='comp', default=None, type=str)
    parser.add_argument('-s', help='Switch East and North components', dest='isswitch', action='store_true')
    parser.add_argument('-b', help='Correct back-azimuth with minimal '
                                   'energy of T component. "baz" is specified '
                                   'as half-searching range. Default value is 90 deg',
                                   dest='baz', nargs='?', const=90, type=float)
    arg = parser.parse_args()
    if arg.comp is not None:
        arg.comp = arg.comp.upper()
        if arg.comp == 'NE' or arg.comp == 'EN':
            reverseE = True
            reverseN = True
        elif arg.comp == 'E':
            reverseE = True
            reverseN = False
        elif arg.comp == 'N':
            reverseE = False
            reverseN = True
        else:
            raise ValueError('component name must be in EN, E or N')
    else:
        reverseN = False
        reverseE = False
    # if arg.baz is not None:
    #     try:
    #         baz_corr = [float(val) for val in arg.b.split('/')]
    #     except:
    #         raise ValueError('Format of baz correction must be as 10/20/45')
    pjt = RF(cfg_file=arg.cfg_file)
    pjt.load_stainfo()
    pjt.search_eq(local=arg.islocal)
    pjt.match_eq(switchEN=arg.isswitch, reverseN=reverseN, reverseE=reverseE)
    pjt.detrend()
    pjt.filter()
    pjt.cal_phase()
    pjt.drop_eq_snr()
    if arg.baz is not None:
        pjt.baz_correct(offset=arg.baz)
    pjt.trim()
    pjt.rotate()
    pjt.deconv()
    pjt.saverf()


def setpar():
    parser = argparse.ArgumentParser(description="Set parameters to configure file")
    parser.add_argument('cfg_file', type=str, help='Path to configure file')
    parser.add_argument('session', type=str, help='session name')
    parser.add_argument('key', type=str, help='key name')
    parser.add_argument('value', type=str, help='value')
    arg = parser.parse_args()
    CfgModify(arg.cfg_file, arg.session, arg.key, arg.value)


if __name__ == '__main__':
    # get_events_test()
    prf()
    # proj_test()
