"""Small CLI that invokes SCALE-Sim without large read/write trace files."""

import argparse

from scalesim.scale_sim import scalesim


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", required=True)
    parser.add_argument("-t", required=True)
    parser.add_argument("-l", required=True)
    parser.add_argument("-p", required=True)
    args = parser.parse_args()
    simulator = scalesim(
        save_disk_space=True,
        verbose=True,
        config=args.c,
        topology=args.t,
        layout=args.l,
        input_type_gemm=True,
    )
    simulator.run_scale(top_path=args.p)


if __name__ == "__main__":
    main()
