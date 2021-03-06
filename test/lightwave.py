import queue
import threading
import socket
import time
import logging

_LOGGER = logging.getLogger(__name__)


class LWLink():
    """LWLink provides a communication link with the LightwaveRF hub."""

    LWRF_REGISTRATION = '100,!F*p'
    SOCKET_TIMEOUT = 2.0
    RX_PORT = 9761
    TX_PORT = 9760

    the_queue = queue.Queue()
    thread = None
    link_ip = ''
    """ ensure registration message is only sent once and only once """
    registration_message_sent = False

    def __init__(self, link_ip=None):
        """Initialise the component."""
        if link_ip is not None:
            LWLink.link_ip = link_ip

    def _send_message(self, msg):
        """Add message to queue and start processing the queue."""
        LWLink.the_queue.put_nowait(msg)
        if LWLink.thread is None or not self.thread.isAlive():
            LWLink.thread = threading.Thread(target=self._send_queue)
            LWLink.thread.start()

    def turn_on_light(self, device_id, name):
        """Create the message to turn light on."""
        msg = '321,!%sFdP32|Turn On|%s' % (device_id, name)

        """ ensure registration message is only sent once and only once """
        LWLink.registration_message_sent = False
        self._send_message(msg)

    def turn_on_switch(self, device_id, name):
        """Create the message to turn switch on."""
        msg = '321,!%sF1|Turn On|%s' % (device_id, name)

        """ ensure registration message is only sent once and only once """
        LWLink.registration_message_sent = False
        self._send_message(msg)

    def turn_on_with_brightness(self, device_id, name, brightness):
        """Scale brightness from 0..255 to 1..32."""
        brightness_value = round((brightness * 31) / 255) + 1
        # F1 = Light on and F0 = light off. FdP[0..32] is brightness. 32 is
        # full. We want that when turning the light on.
        msg = '321,!%sFdP%d|Lights %d|%s' % (
            device_id, brightness_value, brightness_value, name)

        """ ensure registration message is only sent once and only once """
        LWLink.registration_message_sent = False
        self._send_message(msg)

    def turn_off(self, device_id, name):
        """Create the message to turn light or switch off."""
        msg = "321,!%sF0|Turn Off|%s" % (device_id, name)

        """ ensure registration message is only sent once and only once """
        LWLink.registration_message_sent = False
        self._send_message(msg)

    def _send_queue(self):
        """If the queue is not empty, process the queue."""
        while not LWLink.the_queue.empty():
            self._send_reliable_message(LWLink.the_queue.get_nowait())

    def _send_reliable_message(self, msg):
        """Send msg to LightwaveRF hub."""
        result = False
        max_retries = 15
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) \
                    as write_sock, \
                    socket.socket(socket.AF_INET, socket.SOCK_DGRAM) \
                    as read_sock:
                write_sock.setsockopt(
                    socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                read_sock.setsockopt(socket.SOL_SOCKET,
                                     socket.SO_BROADCAST, 1)
                read_sock.settimeout(LWLink.SOCKET_TIMEOUT)
                read_sock.bind(('0.0.0.0', LWLink.RX_PORT))
                while max_retries:
                    max_retries -= 1
                    write_sock.sendto(msg.encode(
                        'UTF-8'), (LWLink.link_ip, LWLink.TX_PORT))
                    result = False
                    while True:
                        response, dummy = read_sock.recvfrom(1024)
                        response = response.decode('UTF-8')
                        if "Not yet registered." in response:
                            _LOGGER.error("Not yet registered")
                            """ ensure registration message is only sent once and only once """
                            if LWLink.registration_message_sent == False:
                                LWLink.registration_message_sent = True
                                self._send_message(LWLink.LWRF_REGISTRATION)

                            result = True
                            break

                        response = response.split(',')[1]
                        if response.startswith('OK'):
                            result = True
                            break

                        if response.startswith('ERR'):
                            break

                    """ if we have an OK response exit """
                    if result:
                        break

                    """ if we have an ERR response, sleep and try again """
                    time.sleep(0.25)

        except socket.timeout:
            _LOGGER.error("LW broker timeout!")
            return result

        except Exception as ex:
            _LOGGER.error(ex)
            raise

        if result:
            _LOGGER.info("LW broker OK!")
        else:
            _LOGGER.error("LW broker fail!")
        return result
