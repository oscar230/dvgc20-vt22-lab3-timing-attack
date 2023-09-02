import requests
from requests.exceptions import ConnectionError, Timeout
import time
import concurrent.futures
from statistics import median, fmean
from typing import Union

#
#   Globals
#

DEBUG: bool = True
CSV: bool = True
HTTP_MAX_RETRIES: int = 32
HTTP_RETRY_SLEEP_BASE: float = 0.5
HTTP_RETRY_SLEEP_FACTOR: float = 0.5
HTTP_LATENCY: float = 0.0
HTTP_LATENCY_TIMOUT_FACTOR: float = 1.5
HTTP_LATENCY_THRESHOLD_FACTOR: float = 0.8
TEST_SAMPLE_SIZE: int = 50
CONCURRENT_WORKERS: int = 8

#
#   Classes
#

class TestResult:
    url: str
    status_code: int
    text: str
    elapsed_time: float

    def __init__(self, url, status_code, text, elapsed_time):
        self.url = url
        self.status_code = status_code
        self.text = text
        self.elapsed_time = elapsed_time

class Auth:
    url: str
    user: str
    delay: float
    tag: list[int]
    tag_max_length: int
    elapsed_time_threshold: float
    sample_size: int
    test_results: list[TestResult]

    def __init__(self, user: str, delay: float, tag: list[int]):
        self.test_results = []
        self.tag_max_length = 32
        self.sample_size = TEST_SAMPLE_SIZE

        self.user = user
        self.delay = delay
        self.tag = tag

        tag_as_string = self.tag_as_string()
        self.url = f"http://dart.cse.kau.se:12345/auth/{int(delay)}/{user}/{tag_as_string}"

        self._run()

        if (DEBUG or CSV) and delay != 0:
            print(f"{self._tag_length()},{self.tag_ok()},{tag_as_string},{'{:.2f}'.format(self.elapsed_time_mean())},{'{:.2f}'.format(self.elapsed_time_median())},{'{:.2f}'.format(self._threshold())},{self.delay},{TEST_SAMPLE_SIZE},{'{:.2f}'.format(HTTP_LATENCY)}")

    # If auth is sucessfull return True
    def ok(self) -> bool:
        return any(r.status_code == 200 for r in self.test_results)
    
    def tag_ok(self) -> bool:
        return self.elapsed_time_mean() > self._threshold()
    
    def _threshold(self) -> float:
        return self.delay * self._tag_length() + (HTTP_LATENCY * HTTP_LATENCY_THRESHOLD_FACTOR)
    
    def _tag_length(self) -> int:
        return len([item for item in self.tag if isinstance(item, int)])
    
    def tag_as_string(self) -> str:
        string = ""
        # represent as string
        for hex_value in self.tag:
            if not isinstance(hex_value, int):
                hex_value = 0
            hex_value = hex(hex_value) # convert
            hex_value = hex_value[2:] # remove the two first characters which are "0x"
            hex_value = pad_string_with_zero(hex_value, 2)
            string += hex_value
        # pad string and return
        return pad_string_with_zero(string, self.tag_max_length)

    def elapsed_time_mean(self) -> float:
        if self.test_results:
            return fmean([item.elapsed_time for item in self.test_results])
        else:
            return 0.0
        
    def elapsed_time_median(self) -> float:
        if self.test_results:
            return median([item.elapsed_time for item in self.test_results])
        else:
            return 0.0

    def _run(self) -> None:
        for _ in range(self.sample_size):
            result = self._request()
            self.test_results.append(result)
    
    def _request(self) -> TestResult:
        timeout: float = self._threshold() + (HTTP_LATENCY * HTTP_LATENCY_TIMOUT_FACTOR)
        if timeout == 0.0:
            timeout = 1337.0
        retried: int = 0

        while retried < HTTP_MAX_RETRIES:
            retry_sleep_time: float = HTTP_RETRY_SLEEP_BASE + (HTTP_RETRY_SLEEP_FACTOR * retried)
            try:
                start_time = time.time()
                response = requests.get(self.url, timeout=timeout)
                end_time = time.time()
                elapsed_time = (end_time - start_time) * 1000
                return TestResult(self.url, response.status_code, response.text, elapsed_time)
            except ConnectionError as e:
                if DEBUG:
                    print(f"Connection failed {e}")
                retried += 1
                if retried < HTTP_MAX_RETRIES:
                    if DEBUG:
                        print(f"Retrying in {retry_sleep_time} ms")
                    time.sleep(retry_sleep_time)
                else:
                    print(f"Max retries of {HTTP_MAX_RETRIES} exceeded!")
                    break
            except Timeout as e:
                print(f"Timeout of {timeout} ms exceeded.")
                retries += 1
                if retries < HTTP_MAX_RETRIES:
                    if DEBUG:
                        print(f"Retrying in {retry_sleep_time} ms")
                    time.sleep(retry_sleep_time)
                else:
                    print(f"Max retries of {HTTP_MAX_RETRIES} exceeded!")
                    break

#
#   Static functions
#

def pad_string_with_zero(input_str, target_length):
    while len(input_str) < target_length:
        input_str += '0'
    return input_str

def full_byte_range_with_prefix(prefix: list[int]) -> list[list[int]]:
    list_of_list = []
    for x in range(256):
        p = prefix.copy()
        p.append(x)
        list_of_list.append(p)
    return list_of_list

def run(user: str, delay: float, tag_prefix: list[int]) -> str:
    tag_prefix_ok: list[Auth] = []

    with concurrent.futures.ThreadPoolExecutor(CONCURRENT_WORKERS) as executor:
        uncompleted_futures = []
        for tag in full_byte_range_with_prefix(tag_prefix):
            uncompleted_futures.append(executor.submit(Auth, user, delay, tag))
        
        for completed_futures in concurrent.futures.as_completed(uncompleted_futures):
            auth_attempt = completed_futures.result()
            if auth_attempt.ok():
                print(auth_attempt)
                # Completed got status 200 return url
                return auth_attempt.url()
            elif auth_attempt.tag_ok():
                # Working tag prefix
                tag_prefix_ok.append(auth_attempt)

    if len(tag_prefix_ok) == 1:
        # Continue with next tag prefix
        return run(user, delay, auth_attempt.tag)
    elif len(tag_prefix_ok) > 1:
        # Too many ok, run again
        return run(user, delay, tag)
    else:
        # Nothing ok, run again
        return run(user, delay, tag)
#
#   Main
#

if __name__ == "__main__":
    user: str = "oscaande104"
    delay: float = float(100)
    
    HTTP_LATENCY = Auth(user, 0, [0x0]).elapsed_time_mean()
    if HTTP_LATENCY > 0:
        if DEBUG or CSV:
            print(f"tag iteration,tag,tag ok,mean,median,threshold,delay,sample size,latency")

        if delay > 0:
            print(f"Done!\nurl={run(user, delay, [])}")
        else:
            print("Delay has to be larger than 0.")
    else:
        print("Failed to get base HTTP latency to server, maybe there is not network connection.")