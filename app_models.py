# -*- coding: utf-8 -*-
from dataclasses import dataclass


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class AudioSegment:
    start: float
    end: float
    path: str
