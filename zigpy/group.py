import logging
from typing import Optional

from zigpy import types as t
from zigpy.device import Device
from zigpy.util import ListenableMixin

LOGGER = logging.getLogger(__name__)


class Group(ListenableMixin, dict):
    def __init__(self, group_id, name=None, groups=None, *args, **kwargs):
        self._groups = groups
        self._group_id = t.Group(group_id)
        self._listeners = {}
        self._name = name
        if groups is not None:
            self.add_listener(groups)
        super().__init__(*args, **kwargs)

    def add_member(self, device: Device, suppress_event=False):
        if not isinstance(device, Device):
            raise ValueError("%s is not %s class" %
                             (device, Device.__class__.__name__))
        if device.ieee in self:
            return self[device.ieee]
        self[device.ieee] = device
        device.member_of[self.group_id] = self
        if not suppress_event:
            self.listener_event('member_added', self, device)
        return self

    def remove_member(self, device: Device, suppress_event=False):
        self.pop(device.ieee, None)
        device.member_of.pop(self.group_id, None)
        if not suppress_event:
            self.listener_event('member_removed', self, device)
        return self

    def __repr__(self):
        return "<{} group_id={} name='{}' members={}>".format(
            self.__class__.__name__, self.group_id, self.name,
            super().__repr__())

    @property
    def group_id(self):
        return self._group_id

    @property
    def members(self):
        return self

    @property
    def name(self):
        if self._name is None:
            return "No name group {}".format(self.group_id)
        return self._name


class Groups(ListenableMixin, dict):
    def __init__(self, app, *args, **kwargs):
        self._application = app
        self._listeners = {}
        super().__init__(*args, **kwargs)

    def add_group(self,
                  group_id: int,
                  name: str = None,
                  suppress_event: bool = False) -> Optional[Group]:
        if group_id in self:
            return self[group_id]
        LOGGER.debug("Adding group: %s, %s", group_id, name)
        group = Group(group_id, name, self)
        self[group_id] = group
        if not suppress_event:
            self.listener_event('group_added', group)
        return group

    def member_added(self, group: Group, device: Device):
        self.listener_event('group_member_added', group, device)

    def member_removed(self, group: Group, device: Device):
        self.listener_event('group_member_removed', group, device)
        if not group:
            self.pop(group)

    def pop(self, item, *args) -> Optional[Group]:
        if isinstance(item, Group):
            group = super().pop(item.group_id, *args)
            self.listener_event('group_removed', group)
            return group
        group = super().pop(item, *args)
        self.listener_event('group_removed', group)
        return group

    remove_group = pop
