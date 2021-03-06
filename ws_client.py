import datetime
import logging
import sys

import simplejson as json
from autobahn.twisted.websocket import WebSocketClientFactory, \
    WebSocketClientProtocol, \
    connectWS
from twisted.internet import reactor
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.python import log

import secure_API
import local_settings

logger = logging.getLogger(__name__)
root = logging.getLogger()
root.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(local_settings.LOG_LEVEL)
formatter = logging.Formatter(
    '%(asctime)s - %(thread)d - %(process)d - %(name)s - %(levelname)s - %(funcName)s -  %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)


class AliveLoggingReceivingCallbackWebsocketClientProtocol(WebSocketClientProtocol):
    """
    Receive only websocket client that logs an alive message when connected.
    """
    alive = False
    callback = None
    alive_message = 'Secure importer alive.'
    tick_interval = 10
    heartbeat_limit = 6

    def onMessage(self, payload, isBinary):
        if not isBinary:
            # print("Text message received: {}".format(payload.decode('utf8')))
            success = self.callback(payload)
            if not success:
                self.factory.relogin()

    def check_health(self):
        """
        Disconnect the websocket if out of protocoll (application level) health check function returns False.

        :return:
        """
        if self.alive:
            try:
                if not self.health_check_func():
                    logger.info("[Protocol] Reconnecting websocket")
                    self.factory.connector.disconnect()
            except Exception as e:
                logger.exception("[Protocol] error in health check %s" % e)
            reactor.callLater(ReloginReconnectingClientFactory.health_check_interval, self.check_health)

    def log_alive(self):
        """
        Log alive flag every interval
        :return:
        """
        if self.alive:
            logger.info(self.alive_message)
            reactor.callLater(ReloginReconnectingClientFactory.log_alive_interval, self.log_alive)

    def connectionMade(self):
        """
        Start logging when connected
        :return:
        """
        self.alive = True
        logger.info('[Protocol %s] connected to websocket' % id(self))

        reactor.callLater(3, self.log_alive)
        # reactor.callLater(3, self.check_health)

        self.factory.resetDelay()
        self.heartBeatCounter = 0
        reactor.callLater(1, self.tick)
        super().connectionMade()

    def connectionLost(self, reason):
        logger.info('[Protocol %s] connection lost ' % id(self))
        self.alive = False

    def tick(self):
        if self.alive:
            self.heartBeatCounter += 1
            logger.info('[Protocol %s] incrementing tick to %s' % (id(self), self.heartBeatCounter))

            if self.heartBeatCounter > self.heartbeat_limit:
                logger.info(
                    '[Protocol {}] no ping for {} * {} seconds -> disconnecting'.format(id(self), self.heartbeat_limit,
                                                                                        self.tick_interval))
                self.transport.loseConnection()
                # self.factory.connector.disconnect()
                return  # do not schedule another tick

            reactor.callLater(self.tick_interval, self.tick)

    def onClose(self, wasClean, code, reason):
        logger.warn("[Protocol {0}] WebSocket connection closed. Reason: {1}".format(id(self), reason))
        super().onClose(wasClean, code, reason)

    def onOpen(self):
        super().onOpen()

    def onConnect(self, response):
        logger.info(
            "[Protocol {}] Connection established. Peer {}, heartbeat {}".format(id(self), self.peer,
                                                                                 self.heartBeatCounter))
        super().onConnect(response)

    def onPing(self, payload):
        self.heartBeatCounter = 0
        logger.info("[Protocol {}] Ping received from {}. Resetting heartbeat counter".format(id(self), self.peer))
        super().onPing(payload)


class ReloginReconnectingClientFactory(ReconnectingClientFactory):
    """
    Changes the websocket server address for a running client.
    """
    health_check_interval = 300
    log_alive_interval = 300

    attempt = 0

    def __init__(self, *args, login_func=None, **kwargs):
        self.login_func = login_func
        super().__init__(*args, **kwargs)

    def relogin(self):
        logger.info('[Factory] logging in again')
        # get the new address
        ws_url = self.login_func()
        # prepare the factory
        self.setSessionParameters(ws_url)
        # disconnect to trigger re-login
        self.connector.disconnect()


class CallbackProtocolFactory(ReloginReconnectingClientFactory, WebSocketClientFactory):
    protocol = AliveLoggingReceivingCallbackWebsocketClientProtocol

    maxDelay = 10
    maxRetries = 10

    def __init__(self, *args, websocketCallback=None, health_check_func=None, **kwargs):
        self.callback = websocketCallback
        self.health_check_func = self.check_gateway_online
        super().__init__(*args, **kwargs)
        self.old_map = None

    def startedConnecting(self, connector):
        logger.debug('[Factory] Started to connect.')

    def clientConnectionLost(self, connector, reason):
        self._p.alive = False

        logger.info('[Factory] Lost connection. Reason: {}'.format(reason))
        if self.attempt < self.maxRetries:
            self.attempt += 1
            logger.info('[Factory] Relogin attempt {}'.format(self.attempt))

            self.relogin()

        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        logger.info('[Factory] Connection failed. Reason: {}'.format(reason))
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

    def buildProtocol(self, addr):
        self._p = WebSocketClientFactory.buildProtocol(self, addr)
        self._p.callback = self.callback
        self._p.health_check_func = self.health_check_func
        return self._p

    @staticmethod
    def datetime_now_string():
        return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f0')

    def check_gateway_online(self):
        """
        Implements the health check for check_health function in AliveLoggingReceivingCallbackWebsocketClientProtocol.

        Must return True if healthy, False otherwise -> triggers disconnection from websocket (and reconnection attempt).

        :return:
        """
        self.secure_server_name = 'test server'
        gateway_last_healthy_update_time = CallbackProtocolFactory.datetime_now_string()
        healthy, new_map = secure_API.check_gateways_online(gateway_last_healthy_update_time)

        # check whether a previously offline gateway is now online
        # the first time this is run, skip
        if self.old_map:
            new_map_hash = hash(frozenset(new_map.items()))
            old_map_hash = hash(frozenset(self.old_map.items()))

            if not old_map_hash == new_map_hash:
                # restart the websocket
                logger.info('Secure server %s reports a change in gateway online status' % self.secure_server_name,
                            extra={"server": self.secure_server_name})
                return False

        # store the old map for the next iteration
        self.old_map = new_map

        if healthy:
            self.gateway_last_healthy_update_time = CallbackProtocolFactory.datetime_now_string()
            logger.info('Secure server %s reports that all gateways are online' % self.secure_server_name,
                        extra={"server": self.secure_server_name})
            return True

        logger.warn('One or more gateways are offline on server %s' % self.secure_server_name,
                    extra={"server": self.secure_server_name})
        return True


def run(ws_url, message_check_capability_push_callback, login_func):
    """

    :param ws_url:
    :param message_check_capability_push_callback: to run with any message received from the websocket
    :param login_func: perform a login to get the websocket url
    :param health_check_func: to run periodically to check health of the websocket
    :return:
    """
    logger.info("url: %s" % ws_url)
    factory = CallbackProtocolFactory(ws_url, websocketCallback=message_check_capability_push_callback,
                                      health_check_func=None, login_func=login_func)

    connector = connectWS(factory)
    factory.connector = connector
    reactor.run()


def capability_push_check_callback(payload):
    response = payload.decode('utf8')
    logger.info("Message received: {}".format(response[:10]))
    data = json.loads(response)
    if data['DataType'] == 1:
        logger.info("Found error code - login again")
        return False
    return True


def get_ws_url():
    ak, ak_id = secure_API.get_auth_tokens()
    # print(ak, ak_id)
    ws_url = secure_API.get_websocket_url(ak, ak_id)

    return ws_url


if __name__ == '__main__':
    log.startLogging(sys.stdout)
    ws_url = get_ws_url()
    run(ws_url, capability_push_check_callback, get_ws_url)
