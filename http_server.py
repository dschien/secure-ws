from http.server import BaseHTTPRequestHandler, HTTPServer
from random import randint

import simplejson as json

# HTTPRequestHandler class
from static_API_messages import login_data, get_gatewaylist_data, get_gateway_data


class testHTTPServer_RequestHandler(BaseHTTPRequestHandler):
    # POST
    def do_POST(self):
        # Send response status code
        self.send_response(200)

        # Send headers
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        # Send message back to client
        message = json.dumps(login_data)
        # Write content as utf-8 data
        self.wfile.write(bytes(message, "utf8"))
        return

    def do_GET(self):
        self.send_response(200)

        # Send headers
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        # Send message back to client


        path = self.path
        if path == '/user/GatewayList':
            message = json.dumps(get_gatewaylist_data(gw_mac_id=47197374102068))

        elif path.startswith('/gateway/gatewaydata'):
            # gcs = 1
            gcs = randint(0, 1)
            message = json.dumps(get_gateway_data(gw_mac_id=47197374102068, gcs=str(gcs)))
        else:
            self.send_response(404, 'NOT FOUND')
            message = '{"message":"not found"}'

        # Write content as utf-8 data
        self.wfile.write(bytes(message, 'UTF-8'))


def run():
    print('starting server...')

    # Server settings
    # Choose port 8080, for port 80, which is normally used for a http server, you need root access
    server_address = ('127.0.0.1', 5679)
    httpd = HTTPServer(server_address, testHTTPServer_RequestHandler)
    print('running server...')
    httpd.serve_forever()


run()
