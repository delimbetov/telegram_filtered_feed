from typing import List


class ContinuousInclusiveInterval:
    def __init__(self, start: int, end: int):
        if end < start:
            raise RuntimeError(f"Invalid interval: end={end} < start={start}")

        self.start = start
        self.end = end

    def includes(self, value: int):
        return self.start <= value <= self.end


class MultiInterval:
    def __init__(self, intervals: List[ContinuousInclusiveInterval]):
        if len(intervals) < 1:
            raise RuntimeError("Invalid multi interval: len < 1")

        self.intervals = intervals

    def includes(self, value: int):
        return any([interval.includes(value) for interval in self.intervals])
