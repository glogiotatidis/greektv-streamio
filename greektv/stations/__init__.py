from greektv.stations import alpha, ant1, ert, mega, skai, star

STATIONS = {
    "mega_tv": {
        "name": "Mega TV",
        "discover": mega.discover,
        "show": mega.show,
        "stream": mega.stream,
    },
    "skai": {
        "name": "Skai",
        "discover": skai.discover,
        "show": skai.show,
        "stream": skai.stream,
    },
    "star_channel": {
        "name": "Star Channel",
        "discover": star.discover,
        "show": star.show,
        "stream": star.stream,
    },
    "alpha_tv": {
        "name": "Alpha TV",
        "discover": alpha.discover,
        "show": alpha.show,
        "stream": alpha.stream,
    },
    "ert": {
        "name": "ERT",
        "discover": ert.discover,
        "show": ert.show,
        "stream": ert.stream,
    },
    "ant1": {
        "name": "ANT1",
        "discover": ant1.discover,
        "show": ant1.show,
        "stream": ant1.stream,
    },
}

ORDER = ["mega_tv", "skai", "star_channel", "alpha_tv", "ert", "ant1"]
