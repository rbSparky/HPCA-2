# Unified anchor lifecycle

Producer and consumer stores are independent. The consumer store holds decoded 2,048-byte tile-slice bitmaps, uses LRU, one read and one write port, record-ID modulo-16 banking, inserts after anchor decode, and releases on eviction/pair completion. At 16 KiB: 72,604 DELTA targets, 422 decoded hits, 72,182 exact padded-record rereads, and zero unclassified targets.
