import asyncio
import enum
import logging
import datetime as dt

import zigpy.endpoint
import zigpy.util
import zigpy.zdo as zdo


LOGGER = logging.getLogger(__name__)


class Status(enum.IntEnum):

    """The status of a Device."""

    # No initialization done
    NEW = 0
    # ZDO endpoint discovery done
    ZDO_INIT = 1
    # Endpoints initialized
    ENDPOINTS_INIT = 2


class Device(zigpy.util.LocalLogMixin):

    """A device on the network."""

    def __init__(self, application, ieee, nwk):
        self._application = application
        self._ieee = ieee
        self.nwk = nwk
        self.path = 'direct'
        self.zdo = zdo.ZDO(self)
        self.endpoints = {0: self.zdo}
        self.lqi = None
        self.rssi = None
        self.last_seen = None
        self.status = Status.NEW
        self.initializing = False
        self.model = None
        self.manufacturer = None
        self.type = 0

    def schedule_initialize(self):
        if self.initializing:
            LOGGER.debug("[0x%04x] Canceling old initialize call",  self.nwk)
            self._init_handle.cancel()
        else:
            self.initializing = True
        self._init_handle = asyncio.ensure_future(self._initialize())

    async def _initialize(self):
        try:
            if self.status == Status.NEW:
                self.info("[0x%04x] Discovering endpoints", self.nwk)
                try:
                    epr = await self.zdo.request(0x0005, self.nwk, tries=3)
                    if epr[0] != 0:
                        raise Exception(
                            "[0x%04x] Endpoint request failed: %s", self.nwk, epr)
                except Exception as exc:
                    self.initializing = False
                    LOGGER.exception(
                        "[0x%04x] Failed ZDO request during device initialization: %s",
                        self.nwk, exc
                    )
                    return

                self.info("[0x%04x] Discovered endpoints: %s", self.nwk, epr[2])
                
                for endpoint_id in epr[2]:
                    self.add_endpoint(endpoint_id)

                self.status = Status.ZDO_INIT
            self.debug("[0x%04x] Endpoints: %s", self.nwk,self.endpoints.keys() )
            for endpoint_id in self.endpoints.keys():
                if endpoint_id == 0:  # ZDO
                    continue
                await self.endpoints[endpoint_id].initialize()

            self.status = Status.ENDPOINTS_INIT
            self.initializing = False
            self._application.device_initialized(self)
        except asyncio.CancelledError:
            LOGGER.debug("[0x%04x] Catched CanceledError",  self.nwk)

    def add_endpoint(self, endpoint_id):
        ep = zigpy.endpoint.Endpoint(self, endpoint_id)
        self.endpoints[endpoint_id] = ep
        return ep

    @property
    def is_sleepy(self):
        try:
            return not (self.type & 8)
        except Exception:
            return True

    async def request(self, profile, cluster, src_ep, dst_ep, sequence, data,
                      expect_reply=True, timeout=15):
        if not self.is_sleepy:
            timeout = 2
        result = await self._application.request(
            self.nwk,
            profile,
            cluster,
            src_ep,
            dst_ep,
            sequence,
            data,
            expect_reply=expect_reply,
            timeout=timeout
        )
        if not result:
            result = [1, ]
        else:
            self.last_seen = dt.datetime.now()
        return result

    def deserialize(self, endpoint_id, cluster_id, data):
        return self.endpoints[endpoint_id].deserialize(cluster_id, data)

    def handle_message(self, is_reply, profile, cluster, src_ep, dst_ep, tsn,
                       command_id, args,  **kwargs):
        message_type = kwargs.get('message_type')
        self.last_seen = dt.datetime.now()
        try:
            endpoint = self.endpoints[src_ep]
        except KeyError:
            self.warn(
                "[0x%04x] Message on unknown endpoint %s",
                self.nwk, src_ep,
            )
            return
        try:
            return endpoint.handle_message(is_reply, profile, cluster, tsn,
                                       command_id, args, 
                                       message_type=message_type)
        except Exception:
            self.debug(
                "[0x%04x:%s] catched Exceptionc for %s - %s",
                self.nwk, src_ep,
                message_type, cluster
                )

    def handle_RouteRecord(self, path):
        self.path = path

    def reply(self, profile, cluster, src_ep, dst_ep, sequence, data):
        return self._application.request(self.nwk, profile, cluster, src_ep,
                                         dst_ep, sequence, data, False)

    def radio_details(self, lqi, rssi):
        self.lqi = lqi
        self.rssi = rssi

    def log(self, lvl, msg, *args):
        msg = '[0x%04x] ' + msg
        args = (self.nwk, ) + args
        return LOGGER.log(lvl, msg, *args)

    @property
    def application(self):
        return self._application

    @property
    def ieee(self):
        return self._ieee

    def __getitem__(self, key):
        return self.endpoints[key]

    def cleanup(self):
        """ do some cleanup to remove cyclic relations."""
        for ep in self.endpoints.values():
            ep._device = None
            ep._status = None
        self.endpoints = None
        if hasattr(self, '_init_handle'):
            if not self._init_handle.done():
                self._init_handle.cancel()
