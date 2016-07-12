import base64
import datetime
import hashlib
import hmac
import logging

# import pylibmc
import requests
import simplejson as json

import local_settings

logger = logging.getLogger(__name__)


def perform_get_request(path):
    """
    Performs a GET request to the specified path, first setting the necessary authorization headers.

    :param path: The request path, appended to the server's HOST
    :returns: The response and the HTTP status code of the request
    """
    url = 'http://{server_address}{path}'.format(
        server_address=local_settings.LOGIN_SERVER_URL, path=path)

    logger.debug("Calling {path}".format(path=path))
    r = requests.get(url)

    res = json.loads(r.content)

    logger.debug(
        'Call to {path} from secure server got response [HTTP Code {code}]'.format(path=path, code=r.status_code),
        extra={'response': json.dumps(res)})

    return res, r.status_code


def get_gateway_list():
    return perform_get_request('/user/GatewayList')


def get_gateway_data(gmacid, last_update_time):
    hexmac = hex(gmacid)
    path = '/gateway/gatewaydata?gatewayMACID={gmacid}&lastupdatetime="{lut}"'.format(gmacid=hexmac,
                                                                                      lut=last_update_time)
    return perform_get_request(path)


SECURE_GCS_CONNECTED = "1"


def check_gateway_online(GMACID, last_update_time):
    res, status_code = get_gateway_data(GMACID, last_update_time)

    if status_code != 200:
        logger.warn('Unable to retrieve gateway data fom {}'.format(GMACID))
        return False

    return res['GDDO']['GCS'] == SECURE_GCS_CONNECTED


def check_gateways_online(last_update_time):
    res, status_code = get_gateway_list()

    if status_code != 200:
        logger.warn('Unable to retrieve list of gateways from {}'.format('test server'))
        return False

    healthy = True
    map = {}

    for gateway in res:
        gmacid = gateway['GMACID']

        this_healthy = check_gateway_online(gmacid, last_update_time)
        map[gmacid] = this_healthy
        if this_healthy:
            logger.info('Gateway {} is online'.format(gmacid))
        else:
            logger.warn('Gateway {} is offline'.format(gmacid))
            healthy = False

    return healthy, map


def update_device_data(data_str, device_parameter):
    path = '/Gateway/UpdateDeviceData'
    url = 'http://{server_address}{path}'.format(server_address=local_settings.SECURE_SERVER_URL, path=path)

    ak, ak_id = get_auth_tokens()
    headers.update(get_extra_headers(ak=ak, ak_id=ak_id, path=path, data_str=data_str))

    r = requests.post(url, data=data_str, headers=headers)

    res = r.json()
    logger.debug('Update call to secure server got response [HTTP Code {}]'.format(r.status_code),
                 extra={'response': res})
    if r.status_code != 200:
        logger.warn("Received error from secure server.", extra={'response': res})
        if r.status_code == 400 and any([i['ID'] == 848 for i in res['ERR']]):
            logger.warn("Received error 848 from secure server. {}".format(res))
            # delete_auth_tokens()
            return update_device_data(data_str, device_parameter)
        logger.error('Update device data failed. [HTTP Code {}]'.format(r.status_code), extra={'response': res})
        raise Exception("Could not update device data: {}".format(data_str))

    return res, r.status_code


def get_extra_headers(ak=None, ak_id=None, path=None, data_str=None):
    date_header = get_dateheader()
    extra_headers = {'DateHeader': date_header}

    if data_str:
        content_md5 = prepare_content_md5(data_str)
        extra_headers['Content-MD5'] = content_md5
        string_to_sign = '\n'.join(['POST', content_md5, date_header, str(ak_id), path.lower()])
    else:
        string_to_sign = '\n'.join(['GET', date_header, str(ak_id), path.lower()])

    digest = hmac.new(ak.encode('utf8'), msg=string_to_sign.encode('utf8'), digestmod=hashlib.sha1).digest()
    signature = base64.b64encode(digest)

    extra_headers['Authorization'] = 'SHS ' + str(ak_id) + ':' + signature.decode('ascii')

    return extra_headers


def prepare_content_md5(content):
    content_md5 = hashlib.md5(content.encode('utf-8')).digest()
    signature = base64.b64encode(content_md5)
    return signature.decode("utf-8")


def login():
    headers.update({'DateHeader': get_dateheader()})
    data = {"UserEMailID": local_settings.SECURE_SERVER_USER,
            "Password": hash_password(local_settings.SECURE_SERVER_PASSWORD)}

    url = 'http://{server_address}/user/{command}'.format(server_address=local_settings.LOGIN_SERVER_URL,
                                                          command='login')
    r = requests.post(url, data=data)

    res = json.loads(r.content)

    # Get Session
    ak = res['SSD']['AK']
    ak_id = res['SSD']['AKID']

    return ak, ak_id, res


def hash_password(password):
    m = hashlib.md5()
    m.update(password.encode("ascii"))
    md5_password = m.hexdigest()
    return md5_password


def get_dateheader():
    # format yyyyMMddTHHmmssfffZ
    dateheader = datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f%Z')[:-3] + 'Z'
    return dateheader


headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}


def get_auth_tokens():
    ak, ak_id, res = login()

    return ak, ak_id


def get_websocket_url(ak, ak_id):
    server = 'ws://%s' % local_settings.SECURE_SERVER_URL
    path = "/WebSocket/ConnectWebSocket".lower()

    date_time = get_dateheader()
    string_to_sign = '\n'.join(['GET', date_time, str(ak_id), path])

    digest = hmac.new(ak.encode('utf8'), msg=string_to_sign.encode('utf8'), digestmod=hashlib.sha1).digest()
    signature = base64.b64encode(digest).decode('ascii')

    connection_url = '{server}{path}?accessKeyID={AKID}&authorization={signature}&date={date_time}'.format(
        server=server,
        path=path,
        AKID=ak_id,
        signature=signature,
        date_time=date_time)

    return connection_url
