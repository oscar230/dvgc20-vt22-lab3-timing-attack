import requests
import time
import concurrent.futures
from statistics import median, fmean

base_elapsed_time = 1000.0
base_elapsed_time_factor = 1.5

def pad_string(input_str, target_length):
    while len(input_str) < target_length:
        input_str += '0'
    return input_str

def hex_array_to_string(hex_array):
    string = ""
    for hex_value in hex_array:
        if not isinstance(hex_value, int):
            hex_value = 0
        hex_value = hex(hex_value) # convert
        hex_value = hex_value[2:] # remove the two first characters which are "0x"
        hex_value = pad_string(hex_value, 2)
        string += hex_value
    return string

def request(user, delay, hex_array):
    tag_max_length = 32

    # Prepare the tag and the url
    tag_formatted_as_string = hex_array_to_string(hex_array) # represent as string
    tag_length = len([item for item in hex_array if isinstance(item, int)])
    tag_formatted_as_string = pad_string(tag_formatted_as_string, tag_max_length) # pad string
    url = f"http://dart.cse.kau.se:12345/auth/{delay}/{user}/{tag_formatted_as_string}"

    # Make request and time the response
    start_time = time.time()
    response = requests.get(url)
    end_time = time.time()
    elapsed_time = end_time - start_time
    elapsed_time = elapsed_time * 1000
    elapsed_time_threshold = delay * tag_length

    result = {
        "status_code": response.status_code,
        "ok": response.status_code == 200,
        "text": response.text,
        "url": url,
        "elapsed_time": "{:.2f}".format(elapsed_time),
        "elapsed_time_threshold": elapsed_time_threshold,
        "delay": delay,
        "hex_array": hex_array,
        "tag": tag_formatted_as_string,
        "tag_ok": elapsed_time >= elapsed_time_threshold,
        "is_tag_full_length": tag_length >= tag_max_length,
        "user": user
    }

    if delay != 0:
        if response.status_code == 400:
            print(f"Malformed input! url={url}")
        if elapsed_time > elapsed_time_threshold + (base_elapsed_time * base_elapsed_time_factor):
            return request(user, delay, hex_array)
        
    return result

def index_of_none(hex_array):    
    try:
        index_of_none = hex_array.index(None)
        return index_of_none
    except ValueError:
        return None

def pwn(user, delay, max_workers, hex_array):
    index = index_of_none(hex_array)
    next_hex_arrays = []
    if isinstance(index, int):
        for r in range(256):
            next_hex_array = hex_array.copy()
            next_hex_array[index] = r
            next_hex_arrays.append(next_hex_array)

    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers) as executor:
        uncompleted_futures = []
        for next_hex_array in next_hex_arrays:
            uncompleted_futures.append(executor.submit(request, user, delay, next_hex_array))
        
        for completed_futures in concurrent.futures.as_completed(uncompleted_futures):
            result = completed_futures.result()
            results.append(result)

    all_elapsed_as_float = [float(item["elapsed_time"]) for item in results]
    if len(all_elapsed_as_float) > 0:
        elapsed_mean = "{:.2f}".format(fmean(all_elapsed_as_float))
        elapsed_median = "{:.2f}".format(median(all_elapsed_as_float))
    else:
        elapsed_mean = "00.00"
        elapsed_median = "00.00"
    for result in results:
        if result["tag_ok"]:
            tag_nice = " ".join(result['tag'][i:i+2] for i in range(0, len(result['tag']), 2)) # found online
            print(f"{tag_nice}\t\t{result['elapsed_time']}\t\t{elapsed_mean}\t\t{elapsed_median}\t\t{result['elapsed_time_threshold']}")
            if result["ok"]:
                print(f"Completed! {result['url']}")
            else:
                next_tag_prefix = result["hex_array"]
                pwn(user, delay, max_workers, next_tag_prefix) # Run another

if __name__ == "__main__":
    user = "oscaande104"
    delay = 98
    max_workers = 4
    array_length = 16
    hex_array = [None] * array_length

    base_elapsed_times = []
    for _ in range(8):
        base_elapsed_times.append(float(request(user, 0, [None])["elapsed_time"]))
    base_elapsed_time = fmean(base_elapsed_times)

    print(f"user\t{user}\ndelay\t{delay} ms\nsize\t{array_length} bytes\nworkers\t{max_workers}\nlatency\t{'{:.2f}'.format(base_elapsed_time)} ({'{:.2f}'.format(base_elapsed_time * base_elapsed_time_factor)})\n\ntag\t\t\t\t\t\t\telapsed\t\tmean\t\tmedian\t\tthreshold")
    pwn(user, delay, max_workers, hex_array)