from io import StringIO

from mosaic_validation.hpca_ramulator import _write_output_line, _write_read_line


def test_hbm_transaction_writer_splits_64b_lines_into_32b_requests():
    read = StringIO(); assert _write_read_line(read, 0x100) == 2
    assert read.getvalue().splitlines() == ["LD 0x100", "LD 0x120"]
    write = StringIO(); assert _write_output_line(write, 0x100) == 4
    assert write.getvalue().splitlines() == ["LD 0x100", "LD 0x120", "ST 0x100", "ST 0x120"]
