import aiofiles
import logging
from os.path import join, dirname
import pickle
import typing
import zigpy.config as conf
from zigpy.device import Device
import zigpy.types as t
from .types import (
    GPCommunicationMode,
    GPSecurityLevel,
    GPSecurityKeyType,
    GreenPowerDeviceID,
    SinkTableEntry
)

LOGGER = logging.getLogger(__name__)

class GreenPowerExtData(t.Struct):
    ieee: t.EUI64
    gpd_id: GreenPowerDeviceID
    sink_table_entry: SinkTableEntry
    counter: t.uint32_t
    unicast_sink: t.EUI64
    key: t.KeyData

    @property
    def communication_mode(self) -> GPCommunicationMode:
        return self.sink_table_entry.communication_mode
    
    @property
    def security_level(self) -> GPSecurityLevel:
        return self.sink_table_entry.security_level
    
    @property 
    def security_key_type(self) -> GPSecurityKeyType:
        return self.sink_table_entry.security_key_type


class GreenPowerExtDB:
    def __init__(self, app) -> None:
        self.__application = app
        self._all_data: typing.List[GreenPowerExtData] = []
        self._data_by_gpid: typing.Dict[GreenPowerDeviceID, GreenPowerExtData] = {}
        self._data_by_ieee: typing.Dict[t.EUI64, GreenPowerExtData] = {}

    @property
    def _filename(self):
        return join(dirname(self.__application.config[conf.CONF_DATABASE]), "zigbee_ext.pkl")

    def contains(self, addr: t.EUI64 | GreenPowerDeviceID):
        return addr in self._data_by_gpid or addr in self._data_by_ieee

    def get(self, addr: t.EUI64 | GreenPowerDeviceID) -> GreenPowerExtData | None:
        if addr in self._data_by_gpid:
            return self._data_by_gpid[addr]
        if addr in self._data_by_ieee:
            return self._data_by_ieee[addr]
        return None
    
    async def remove(self, device: Device):
        idx = next((i for i, e in enumerate(self._all_data) if e.ieee == device.ieee), None)
        if idx is not None:
            entry = self._all_data[idx]
            del self._all_data[idx]
            del self._data_by_gpid[entry.gpd_id]
            del self._data_by_ieee[entry.ieee]
            await self.write_to_disk()
        else:
            LOGGER.error("GPExtDB got remove request for %s but not present; failing", str(device.ieee))

    async def add(self, data:GreenPowerExtData):
        # find first duplicate index
        idx = next((i for i, e in enumerate(self._all_data) if e.gpd_id == data.gpd_id), None)
        if idx is not None:
            self._all_data[idx] = data
        else:
            self._all_data.append(data)
        self._data_by_gpid[data.gpd_id] = data
        self._data_by_ieee[data.ieee] = data
        await self.write_to_disk()

    async def load(self):
        self._all_data = []
        LOGGER.debug("Starting Ext DB load...")
        try:
            async with aiofiles.open(self._filename, mode='rb') as f:
                contents = await f.read()
                self._all_data = pickle.loads(contents)
        except:
            pass
        LOGGER.debug("Ext DB load complete!")
        self._data_by_gpid = {e.gpd_id:e for e in self._all_data}
        self._data_by_ieee = {e.ieee:e for e in self._all_data}

    async def write_to_disk(self):
        LOGGER.debug("Starting Ext DB save...")
        pickled = pickle.dumps(self._all_data)
        database_file = self
        async with aiofiles.open(self._filename, mode='wb') as out:
            await out.write(pickled)
            await out.flush()
            LOGGER.debug("Ext DB save complete!")
        
