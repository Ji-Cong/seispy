from os.path import expanduser, join, exists, dirname
import os
import obspy


class para(object):
    def __init__(self):
        self.datapath = expanduser('~')
        self.rfpath = expanduser('~')
        self.imagepath = expanduser('~')
        self.catalogpath = join(dirname(__file__), 'data', 'EventCMT.dat')
        self.catalog_server = 'IRIS'
        self.offset = None
        self.tolerance = 210
        self.dateformat = '%Y.%j.%H.%M.%S'
        self.date_begin = obspy.UTCDateTime('19760101')
        self.date_end = obspy.UTCDateTime.now()
        self.catalog_server = 'IRIS'
        self.magmin = 5.5
        self.magmax = 10
        self.dismin = 30
        self.dismax = 90
        self.ref_comp = 'BHZ'
        self.suffix = 'SAC'
        self.noisegate = 5
        self.noiselen = 50
        self.gauss = 2
        self.target_dt = 0.01
        self.phase = 'P'
        self.time_before = 10
        self.time_after = 120
        self.freqmin = 0.05
        self.freqmax = 1
        self.itmax = 400
        self.minderr = 0.001
        self.criterion = 'crust'
        self.only_r = False

    def get_para(self):
        return self.__dict__

    @property
    def datapath(self):
        return self._datapath

    @datapath.setter
    def datapath(self, value):
        if not isinstance(value, str):
            raise TypeError('datapath should be \'str\' type not \'{0}\''.format(type(value)))
        elif not exists(value):
                raise FileExistsError('No such find data path of {0}'.format(value))
        else:
            self._datapath = value

    @property
    def rfpath(self):
        return self._rfpath

    @rfpath.setter
    def rfpath(self, value):
        if not isinstance(value, str):
            raise TypeError('rfpath should be \'str\' type not \'{0}\''.format(type(value)))
        elif not exists(value):
            try:
                os.makedirs(value)
            except Exception as e:
                Warning('Cannot create rfpath of {0}\n with error: {1}'.format(value, e))
            finally:
                self._rfpath = value
        else:
            self._rfpath = value

    @property
    def imagepath(self):
        return self._imagepath

    @imagepath.setter
    def imagepath(self, value):
        if not isinstance(value, str):
            raise TypeError('imagepath should be \'str\' type not \'{0}\''.format(type(value)))
        elif not exists(value):
            try:
                os.makedirs(value)
            except Exception as e:
                Warning('Cannot create rfpath of {0}\n with error: {1}'.format(value, e))
            finally:
                self._imagepath = value
        else:
            self._imagepath = value

    @property
    def catalogpath(self):
        return self._catalogpath

    @catalogpath.setter
    def catalogpath(self, value):
        if not isinstance(value, str):
            raise TypeError('catalogpath should be \'str\' type not \'{0}\''.format(type(value)))
        self._catalogpath = value

    @property
    def criterion(self):
        return self._criterion

    @criterion.setter
    def criterion(self, value):
        if value == '':
            self._criterion = None
        else:
            self._criterion = value
