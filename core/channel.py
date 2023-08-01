from kante.channel import build_channel


image_broadcast, image_listen = build_channel("image")
provenance_broadcast, provenance_listen = build_channel("provenance")
