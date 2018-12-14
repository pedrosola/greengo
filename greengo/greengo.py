import os
import errno
import fire
import json
import yaml
# import shutil
# import urllib
import logging
from boto3 import session
# from botocore.exceptions import ClientError

import utils
from entity import Entity
from group import Group
from subscriptions import Subscriptions

logging.basicConfig(
    format='%(asctime)s|%(name).10s|%(levelname).5s: %(message)s',
    level=logging.WARNING)

log = logging.getLogger('greengo')
log.setLevel(logging.DEBUG)


DEFINITION_FILE = 'greengo.yaml'
MAGIC_DIR = '.gg'
STATE_FILE = os.path.join(MAGIC_DIR, 'gg_state.json')

DEPLOY_TIMEOUT = 90  # Timeout, seconds


class State(object):

    def __init__(self, file):
        # Entities map: { entityName: entity }
        self._file = file
        self._entities = {}
        self._state = {}

        self.load()

    def load(self):
        if not os.path.exists(self._file):
            log.debug("Group state file {0} not found, assume new group.".format(self._file))
        else:
            log.debug("Loading group state from {0}".format(self._file))
            with open(self._file, 'r') as f:
                self._state = json.load(f)

    def save(self):
        try:
            with open(self._file, 'w') as f:
                json.dump(self._state, f, indent=2,
                          separators=(',', ': '), sort_keys=True, default=str)
                log.debug("Updated group state in state file '{0}'".format(self._file))
        except IOError as e:
            # Assume we miss the directory... Create it and try again
            if e.errno != errno.ENOENT:
                raise e
            utils.mkdir(os.path.dirname(self._file))
            self.save()

    def exists(self):
        return bool(self._state)

    def update(self, key, body):
        self._state[key] = body
        self.save()

    def get(self, key=None, default=None):
        if key:
            return self._state.get(key, default)
        return self._state

    def checkpoint(self, entity):
        # 1. update entity in a map (I'll need entity name... )
        # 2. save in file
        pass

    def remove(self):
        self.state = {}
        try:
            os.remove(self._file)
        except OSError:
            log.warning("State file not removed (missing?): {}".format(self._file))


class Commands(object):
    def __init__(self):

        s = session.Session()
        self._region = s.region_name
        if not self._region:
            log.error("AWS credentials and region must be setup. "
                      "Refer AWS docs at https://goo.gl/JDi5ie")
            exit(-1)

        log.info("AWS credentials found for region '{}'".format(self._region))

        Entity._session = s

        self._gg = s.client("greengrass")
        self._iot = s.client("iot")
        self._lambda = s.client("lambda")
        self._iam = s.client("iam")
        self._iot_endpoint = self._iot.describe_endpoint()['endpointAddress']

        try:
            with open(DEFINITION_FILE, 'r') as f:
                self.group = self.group = yaml.safe_load(f)
        except IOError:
            log.error("Group definition file `greengo.yaml` not found. "
                      "Create file, and define the group definition first. "
                      "See https://github.com/greengo for details.")
            exit(-1)

        self.state = State(STATE_FILE)

        self.name = self.group['Group']['name']

    def create(self):
        if self.state.get():
            log.error("Previously created group exists. Remove before creating!")
            return False

        log.info("[BEGIN] creating group {0}".format(self.group['Group']['name']))

        Group(self.group, self.state).create(update_group_version=False)

        Subscriptions(self.group, self.state).create(update_group_version=False)

        # Create other entities like this...

        Group.create_group_version(self.state)

        log.info("[END] creating group {0}".format(self.group['Group']['name']))

    def remove(self):
        if not self.state.get():
            log.info("There seem to be nothing to remove.")
            return False

        log.info("[BEGIN] removing group {0}".format(self.group['Group']['name']))

        Group(self.group, self.state).remove()

        self.state.remove()

        log.info("[END] removing group {0}".format(self.group['Group']['name']))

    def create_subscriptions(self, update_group_version=True):
        log.info("Subscription definition created OK!")

    def remove_subscriptions(self):
        log.info("Subscription definition removed OK!")


def main():
    fire.Fire(Commands)

if __name__ == '__main__':
    main()
