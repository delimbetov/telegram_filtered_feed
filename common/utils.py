def circular_generator(l: list):
    if len(l) < 1:
        raise RuntimeError("Circular generator expects non empty list")

    curr_idx = 0

    while True:
        yield l[curr_idx]
        curr_idx += 1
        curr_idx = 0 if curr_idx >= len(l) else curr_idx
