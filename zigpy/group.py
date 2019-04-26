import logging

LOGGER = logging.getLogger(__name__)


class Group:
    def add_member(self, device):
        pass


class Groups:
    def __init__(self, app):
        self._application = app

    def add_group(self, group_id, name):
        pass

    def __getitem__(self, item):
        return Group()
