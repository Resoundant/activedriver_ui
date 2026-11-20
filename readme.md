# Active Driver clients

Python and C# tools for communicating with a Resoundant Active Driver over UDP.
Send device text commands, read replies, or use the Python desktop interfaces
to send commands and preview multi-frequency waveforms.

| Implementation | Includes | Documentation |
| --- | --- | --- |
| Python | Command GUI, multi-frequency waveform GUI, command-line client, and reusable device API/UDP transport. | [Python setup and GUI launch guide](python/readme.md) |
| C# | Command-line client and reusable `ActiveDriverUdp` class targeting .NET Framework 4.8 and 4.6.1. | [C# build and usage guide](cs/readme.md) |

The clients default to device IP `10.0.1.30` and UDP port `2000`, with local
response port `2000`. Device communication requires a reachable Active Driver
and a suitable local network adapter. The Python waveform preview and text
export can be used without hardware.

See the Active Driver communications manual for the complete device command
reference.
