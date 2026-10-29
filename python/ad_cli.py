"""
Send a command to an Active Driver via UDP and print its responses.

"""

import argparse

from udp import ActiveDriverUdp, find_adapter_for_ip


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", help="Text command to send, e.g. '?V' or '+F60'")
    parser.add_argument("--ad-ip", default="10.0.1.30", help="Active Driver IP address")
    parser.add_argument("--ad-port", type=int, default=2000, help="Active Driver UDP port")
    parser.add_argument("--host-ip", help="Local IP address (default: detect matching adapter for ad-ip)")
    parser.add_argument("--host-port", type=int, default=2000, help="Local UDP response port")
    parser.add_argument(
        "--timeout", type=float, default=0.2,
        help="Seconds to wait for additional replies after each response (default: 0.2)",
    )
    args = parser.parse_args()
    if not 0 < args.timeout < float("inf"):
        parser.error("--response-wait must be a positive, finite number")

    host_ip = args.host_ip
    if host_ip is None:
        _, host_ip, _ = find_adapter_for_ip(args.ad_ip)
        if host_ip is None:
            parser.error(f"No network adapter found for {args.ad_ip}; specify --host-ip")

    with ActiveDriverUdp(args.ad_ip, args.ad_port, host_ip, args.host_port) as driver:
        driver.SendCmd(args.command)
        responses = driver.GetUdpResponse(args.timeout)
        while responses != [""]:
            for response in responses:
                print(response, flush=True)
            responses = driver.GetUdpResponse(args.timeout)


if __name__ == "__main__":
    main()
