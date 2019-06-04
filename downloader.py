import sys
import os
import logging

from cbapi.response import Process, CbResponseAPI, Sensor
from cbapi.response.models import Sensor as CB_Sensor
import cbapi.errors


_MOD_LOGGER = logging.getLogger(__name__)
_MOD_LOGGER.setLevel(logging.INFO)
_log_handler = logging.StreamHandler()
_log_handler.setLevel(logging.INFO)
_log_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
_MOD_LOGGER.addHandler(_log_handler)



#reload(sys)

# def download_files(path, file_list, destination_dir):
#     for file in file_list:


#TODO check if the machine is online before connecting (correlate with attempts)

def main():
    hostname = "IT10009447W1"
    destination_dir = "."
    path = "c:\\maintenance\\pownv3\\"
    filter = "IT10009447W1.Out.7z.001."
    file_download_timeout = 120 # in seconds
    limit_attempts = 0
    cb = CbResponseAPI()

    sensor = cb.select(Sensor).where("hostname:"+hostname).first()

    attempt = 0
    while attempt < limit_attempts or not limit_attempts:
        try:
            _MOD_LOGGER.info(f"Trying to establish LR. Attempt {attempt}")
            with sensor.lr_session() as session:
                _MOD_LOGGER.info(f"Established session Id {session.session_id}")
                dir_list = session.list_directory(path)
                for entry in dir_list:
                    if "ARCHIVE" in entry["attributes"] and entry["filename"].startswith(filter):
                        dest_path = os.path.join(destination_dir, entry["filename"])
                        #find out if the file has been correctly downloaded already
                        if os.path.exists(dest_path) and os.path.getsize(dest_path) == entry["size"]:
                                _MOD_LOGGER.info(f"File {entry['filename']} already downloaded. Skipping.")
                                continue

                        #try to download the complete file until the end of the time
                        _MOD_LOGGER.info(f"Downloading file {entry['filename']}, size {entry['size']}...")
                        while True:
                            content = session.get_file(path + entry["filename"], file_download_timeout)
                            if entry["size"] == len(content):
                                #TODO save the file
                                with open(dest_path, "wb") as file_output:
                                    file_output.write(content)
                                _MOD_LOGGER.info("* Download completed.")
                                break
                            else:
                                _MOD_LOGGER.info("* Download failed. Trying again.")

            break #"everything" was successful, leave while outer loop
        except cbapi.errors.TimeoutError as e:
            attempt += 1
            _MOD_LOGGER.exception(f"Attempt {attempt}/{limit_attempts} failed.")
            #print(e)

    #print(sensor)

#TIP when listing directories, tha final backslash is important

# {'last_access_time': 1557479642, 'last_write_time': 1557479621, 'filename': 'pcr1_11.txt', 'create_time': 1557479642, 'attributes': ['ARCHIVE'], 'size': 0}

# ======== ERROR MISSED SESSION ===============
# Traceback (most recent call last):
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\response\cblr.py", line 27, in _get_or_create_session
#     desired_status="active", delay=1, timeout=360)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\live_response_api.py", line 921, in poll_status
#     raise TimeoutError(uri=url, message="timeout polling for Live Response")
# cbapi.errors.TimeoutError: Timed out when requesting /api/v1/cblr/session/32 from API: timeout polling for Live Response
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#   File "main.py", line 74, in <module>
#     main()
#   File "main.py", line 15, in main
#     with sensor.lr_session() as session:
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\response\models.py", line 736, in lr_session
#     return self._cb._request_lr_session(self._model_unique_id)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\response\rest_api.py", line 190, in _request_lr_session
#     return self.live_response.request_session(sensor_id)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\live_response_api.py", line 873, in request_session
#     session_id, session_data = self._get_or_create_session(sensor_id)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\response\cblr.py", line 35, in _get_or_create_session
#     error_code=404)
# cbapi.errors.TimeoutError: Timed out when requesting /api/v1/cblr/session/32 from API with HTTP status code 404: Could not establish session with sensor 395

# ['MAX_RETRY_COUNT', '__class__', '__delattr__', '__dict__', '__dir__', '__doc__',
# '__enter__', '__eq__', '__exit__', '__format__', '__ge__', '__getattribute__', '__gt__',
# '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__', '__new__',
# '__reduce__', '__reduce_ex__', '__repr__', '__setattr__', '__sizeof__', '__str__', '__subclasshook__',
# '__weakref__', '_cb', '_cblr_manager', '_closed', '_lr_post_command', '_poll_command', '_random_file_name',
# '_refcount', '_upload_file', 'cblr_base', 'close', 'create_directory', 'create_process',
# 'create_registry_key', 'delete_file', 'delete_registry_key', 'delete_registry_value', 'get_file',
# 'get_raw_file', 'get_registry_value', 'get_session_archive', 'kill_process', 'list_directory',
# 'list_processes', 'list_registry_keys', 'list_registry_keys_and_values', 'memdump', 'os_type',
# 'path_islink', 'path_join', 'put_file', 'sensor_id', 'session_data', 'session_id',
# 'set_registry_value', 'start_memdump', 'walk']

# ======== ERROR PROXY AUTHENTICATION ===============
#
# Traceback (most recent call last):
#   File "c:\tools\scripts\cb_test\lib\site-packages\urllib3\connectionpool.py", line 594, in urlopen
#     self._prepare_proxy(conn)
#   File "c:\tools\scripts\cb_test\lib\site-packages\urllib3\connectionpool.py", line 805, in _prepare_proxy
#     conn.connect()
#   File "c:\tools\scripts\cb_test\lib\site-packages\urllib3\connection.py", line 308, in connect
#     self._tunnel()
#   File "c:\tools\Python37\lib\http\client.py", line 911, in _tunnel
#     message.strip()))
# OSError: Tunnel connection failed: 407 Proxy Authentication Required
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#   File "c:\tools\scripts\cb_test\lib\site-packages\requests\adapters.py", line 449, in send
#     timeout=timeout
#   File "c:\tools\scripts\cb_test\lib\site-packages\urllib3\connectionpool.py", line 667, in urlopen
#     **response_kw)
#   File "c:\tools\scripts\cb_test\lib\site-packages\urllib3\connectionpool.py", line 667, in urlopen
#     **response_kw)
#   File "c:\tools\scripts\cb_test\lib\site-packages\urllib3\connectionpool.py", line 667, in urlopen
#     **response_kw)
#   [Previous line repeated 1 more times]
#   File "c:\tools\scripts\cb_test\lib\site-packages\urllib3\connectionpool.py", line 638, in urlopen
#     _stacktrace=sys.exc_info()[2])
#   File "c:\tools\scripts\cb_test\lib\site-packages\urllib3\util\retry.py", line 398, in increment
#     raise MaxRetryError(_pool, url, error or ResponseError(cause))
# urllib3.exceptions.MaxRetryError: HTTPSConnectionPool(host='just-hawk2.my.cbcloud.de', port=443): Max retries exceeded with url: /api/v1/cblr/session/60/command/91 (Caused by ProxyError('Cannot connect to proxy.', OSError('Tunnel connection failed: 407 Proxy Authentication Required')))
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\connection.py", line 176, in http_request
#     timeout=self._timeout, **kwargs)
#   File "c:\tools\scripts\cb_test\lib\site-packages\requests\sessions.py", line 533, in request
#     resp = self.send(prep, **send_kwargs)
#   File "c:\tools\scripts\cb_test\lib\site-packages\requests\sessions.py", line 646, in send
#     r = adapter.send(request, **kwargs)
#   File "c:\tools\scripts\cb_test\lib\site-packages\requests\adapters.py", line 510, in send
#     raise ProxyError(e, request=request)
# requests.exceptions.ProxyError: HTTPSConnectionPool(host='just-hawk2.my.cbcloud.de', port=443): Max retries exceeded with url: /api/v1/cblr/session/60/command/91 (Caused by ProxyError('Cannot connect to proxy.', OSError('Tunnel connection failed: 407 Proxy Authentication Required')))
#
# During handling of the above exception, another exception occurred:
#
# Traceback (most recent call last):
#   File "main.py", line 150, in <module>
#     main()
#   File "main.py", line 56, in main
#     content = session.get_file(path + entry["filename"], file_download_timeout)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\live_response_api.py", line 117, in get_file
#     fp = self.get_raw_file(file_name, timeout=timeout, delay=delay)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\live_response_api.py", line 101, in get_raw_file
#     self._poll_command(command_id, timeout=timeout, delay=delay)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\live_response_api.py", line 564, in _poll_command
#     **kwargs)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\live_response_api.py", line 912, in poll_status
#     res = cb.get_object(url)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\connection.py", line 258, in get_object
#     result = self.api_json_request("GET", uri)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\connection.py", line 280, in api_json_request
#     result = self.session.http_request(method, uri, headers=headers, data=raw_data, **kwargs)
#   File "c:\tools\scripts\cb_test\lib\site-packages\cbapi\connection.py", line 185, in http_request
#     original_exception=connection_error)
# cbapi.errors.ApiError: Received a network connection error from https://just-hawk2.my.cbcloud.de: HTTPSConnectionPool(host='just-hawk2.my.cbcloud.de', port=443): Max retries exceeded with url: /api/v1/cblr/session/60/command/91 (Caused by ProxyError('Cannot connect to proxy.', OSError('Tunnel connection failed: 407 Proxy Authentication Required')))



# def main():
#     api = CbResponseAPI()
#
#
#
#     query = api.select(Process).where("sensor_id:395")
#
#     # for proc in query:
#     #     for fm in proc.filemods:
#     #         print(proc.process_name, fm.path)
#
#     example = query.first()
#     #example = query[2]
#
#     print(example)
#     print("*"*80)
#     print(example.filemods, example.modloads)
#     print(dir(example.filemods))
#
#     for a in example.all_events_segment:
#         print(a)
#
#     # for fm in example.filemods:
#     #     print(fm.path)
#     #     print(fm)
#     #     #break
#     # for ml in example.modloads:
#     #     print(ml)
#     #
#     # for nc in example.netconns:
#     #     print(nc)


if __name__ == '__main__':
    main()
