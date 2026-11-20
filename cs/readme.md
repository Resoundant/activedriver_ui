# Active Driver C# client

This project implements a simple command-line tool that sends ASCII text commands to a
Resoundant Active Driver over UDP and prints its responses. `main.cs` provides the command-line tool.

`ad_udp.cs` provides the reusable `ActiveDriverUdp` class for sending and receiving messages from the active driver.


## Building

The project targets .NET Framework 4.8 (`net48`) and .NET Framework 4.6.1
(`net461`). It uses C# 7.3 with explicit `using` statements. Use build tools
with C# 7.3 support, such as Visual Studio 2019 with the appropriate .NET
Framework targeting packs, or a compatible .NET SDK for the commands below.

Run these PowerShell commands from this project's `cs` directory:

```powershell
# Restore dependencies and build both targets.
dotnet build .\ad_cli.csproj --configuration Release

# Or build only the required target.
dotnet build .\ad_cli.csproj --configuration Release --framework net48
dotnet build .\ad_cli.csproj --configuration Release --framework net461
```

The build restores packages automatically. NuGet access may be needed to obtain
.NET Framework reference assemblies when the corresponding targeting packs
are not installed. The build output reports the generated files' locations.
For .NET Framework, run the generated `ad_cli.exe` on Windows with the matching
or a compatible later .NET Framework installed.

## Command-line usage

The tool sends one command, prints each response on its own line, and exits
when no further responses arrive within the timeout, or a batch contains only
an empty response. Quote commands containing spaces. Commands must be ASCII.

```text
ad_cli <command> [--ad-ip IP] [--ad-port PORT] [--host-ip IP] [--host-port PORT] [--timeout SECONDS]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--ad-ip` | `10.0.1.30` | Active Driver IPv4 address. |
| `--ad-port` | `2000` | Device UDP destination port. |
| `--host-ip` | Automatic | Local IPv4 address to receive responses on; automatically selects the first adapter address on the device's subnet. |
| `--host-port` | `2000` | Local UDP receive port. *This must match the active driver "UDP output" port* |
| `--timeout` | `0.2` | Positive, finite wait in seconds for each response batch. |
| `--help`, `-h` | | Print usage and exit without contacting the device. |

From the directory containing the built `ad_cli.exe`, query the device version:

```powershell
.\ad_cli.exe --help

# Factory default IP 10.0.1.30, port 2000
.\ad_cli.exe '?V' 

# Choose a specific local adapter and a longer response wait.
.\ad_cli.exe '?V' --ad-ip 192.168.6.2 --timeout 0.5

# Send an entire profile: 55% amplitude, 60Hz, 10 cycles, 0.5s soft start
.\ad_cli.exe '+A55+F60+D10+r0.5' 

```

Before sending your command, the tool's UDP client sends `?v` and waits up to
0.5 seconds for an initialization response. This response is consumed internally.
The `--timeout` option does not change that initialization wait.

Exit codes are `0` for normal completion, `2` for argument errors, and `1` for
other failures. Errors are written to standard error. A timeout after sending
the requested command ends normally, so exit code `0` does not confirm that
the device acknowledged that command.

## Using `ad_udp.cs` directly

Include `ad_udp.cs` in your own C# project to use `ActiveDriverUdp` without the
command-line parser. Use C# 7.3 or later, as configured in `ad_cli.csproj`.
The file includes all required `using` statements. Reference values can be
`null`; in particular, check the result of `FindAdapterAddress` before use.

| Member | Behavior |
| --- | --- |
| `FindAdapterAddress(IPAddress target)` | Returns the first local IPv4 address whose subnet matches the target - the active driver IP - or `null` if none matches. |
| `ActiveDriverUdp(deviceAddress, devicePort, localAddress, localPort)` | Binds the receive socket, starts a background listener, and checks communication with `?v`. Throws `InvalidOperationException` if initialization fails; inspect `InnerException` for the cause. |
| `Send(string command)` | Clears queued responses and sends the command using ASCII encoding. Drain responses before sending another command. |
| `GetUdpResponse(double timeoutSeconds)` | Returns and removes the currently queued responses as a `List<string>`, waiting up to the supplied timeout if no responses are received. Returns an empty list on timeout; throws if the receiver is closed and no messages remain. |
| `Dispose()` | Closes the receive socket, clears queued responses, and joins the listener thread. Use a `using` block to ensure cleanup. |

This example can be used as a separate application's entry point with
`ad_udp.cs` included in that project:

```csharp
using System;
using System.Net;

internal static class Example
{
    private static void Main()
    {
        var deviceAddress = IPAddress.Parse("192.168.6.2");
        var localAddress = ActiveDriverUdp.FindAdapterAddress(deviceAddress)
            ?? throw new InvalidOperationException("No adapter on the device subnet.");
        // Alternatively: var localAddress = IPAddress.Parse("192.168.6.10");

        using (var driver = new ActiveDriverUdp(deviceAddress, 2000, localAddress, 2000))
        {
            driver.Send("?V");

            while (true)
            {
                var responses = driver.GetUdpResponse(0.2);
                if (responses.Count == 0 ||
                    (responses.Count == 1 && responses[0] == ""))
                    break;

                foreach (string response in responses)
                    Console.WriteLine(response);
            }
        }
    }
}
```

Responses are decoded as UTF-8 with trailing null characters removed. Use
ASCII commands and positive, finite timeout values when calling the class
directly; it does not perform the CLI's input validation. 

See the Active Driver communications manual for the full command list.

If initialization times out, check the device address, selected local adapter,
UDP ports, network connection, and firewall rules allowing incoming responses
on the local receive port (2000 by default).
