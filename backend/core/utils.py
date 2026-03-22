import concurrent.futures


def run_in_thread(func, *args):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(func, *args).result()
