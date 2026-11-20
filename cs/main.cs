using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net;
using System.Net.Sockets;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            string command = null;
            string adIp = "10.0.1.30";
            string hostIp = null;
            int adPort = 2000;
            int hostPort = 2000;
            double timeout = 0.2;
            bool positionalOnly = false;

            for (int i = 0; i < args.Length; i++)
            {
                string arg = args[i];
                if (!positionalOnly && (arg == "--help" || arg == "-h"))
                {
                    Console.WriteLine("Send a text command to an Active Driver and print its UDP responses.");
                    Console.WriteLine("Usage: ad_cli <command> [--ad-ip IP] [--ad-port PORT] [--host-ip IP] [--host-port PORT] [--timeout SECONDS]");
                    Console.WriteLine("Defaults: --ad-ip 10.0.1.30 --ad-port 2000 --host-port 2000 --timeout 0.2");
                    Console.WriteLine("The local IPv4 address is detected from the device subnet unless --host-ip is supplied.");
                    Console.WriteLine("Use --host-port 0 to receive inline on the sending socket's OS-assigned port, without a listener thread.");
                    Console.WriteLine("Example: ad_cli '?V' --ad-ip 192.168.6.2");
                    return 0;
                }
                if (!positionalOnly && arg == "--")
                {
                    positionalOnly = true;
                    continue;
                }
                if (!positionalOnly && arg.StartsWith("-", StringComparison.Ordinal))
                {
                    int separator = arg.IndexOf('=');
                    string option = separator < 0 ? arg : arg.Substring(0, separator);
                    if (option != "--ad-ip" && option != "--ad-port" && option != "--host-ip" &&
                        option != "--host-port" && option != "--timeout")
                        throw new ArgumentException("Unknown option: " + option);
                    string value;
                    if (separator >= 0)
                        value = arg.Substring(separator + 1);
                    else if (++i < args.Length)
                        value = args[i];
                    else
                        throw new ArgumentException("Missing value for " + option);

                    switch (option)
                    {
                        case "--ad-ip": adIp = value; break;
                        case "--host-ip": hostIp = value; break;
                        case "--ad-port": adPort = ParsePort(value, option); break;
                        case "--host-port": hostPort = ParsePort(value, option); break;
                        case "--timeout":
                            if (!double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out timeout) ||
                                timeout <= 0 || double.IsNaN(timeout) || double.IsInfinity(timeout))
                                throw new ArgumentException("--timeout must be a positive, finite number");
                            break;
                    }
                }
                else if (command == null)
                    command = arg;
                else
                    throw new ArgumentException("Only one command may be supplied; quote commands containing spaces");
            }

            if (command == null)
                throw new ArgumentException("A command is required; use --help for usage");
            foreach (char character in command)
                if (character > 127)
                    throw new ArgumentException("Commands must contain only ASCII characters");

            IPAddress deviceAddress = ParseAddress(adIp, "--ad-ip");
            IPAddress localAddress = hostIp == null ? ActiveDriverUdp.FindAdapterAddress(deviceAddress) : ParseAddress(hostIp, "--host-ip");
            if (localAddress == null)
                throw new ArgumentException("No network adapter found for " + adIp + "; specify --host-ip");

            using (var driver = new ActiveDriverUdp(deviceAddress, adPort, localAddress, hostPort))
            {
                driver.Send(command);
                while (true)
                {
                    List<string> responses = driver.GetUdpResponse(timeout);
                    if (responses.Count == 0 || (responses.Count == 1 && responses[0] == ""))
                        break;
                    foreach (string response in responses)
                        Console.WriteLine(response);
                    Console.Out.Flush();
                }
            }
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine("Error: " + exception.Message);
            return exception is ArgumentException ? 2 : 1;
        }
    }

    private static int ParsePort(string value, string option)
    {
        int port;
        int minimum = option == "--host-port" ? 0 : 1;
        if (!int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out port) || port < minimum || port > 65535)
            throw new ArgumentException(option + " must be between " + minimum + " and 65535");
        return port;
    }

    private static IPAddress ParseAddress(string value, string option)
    {
        IPAddress address;
        if (!IPAddress.TryParse(value, out address) || address.AddressFamily != AddressFamily.InterNetwork)
            throw new ArgumentException(option + " must be an IPv4 address");
        return address;
    }
}
