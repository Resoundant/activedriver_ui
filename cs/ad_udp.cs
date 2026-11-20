/*
 * ad_udp.cs
 *
 * A low-level implmeentation of a UDP sender/receiver to communicate commands and responses 
 * from the resoundant Active Driver.
 * 
 * Example usage:
 *
 * var deviceAddress = IPAddress.Parse("10.0.1.30");
 * var devicePort = 2000;
 * var localAddress = ActiveDriverUdp.FindAdapterAddress(deviceAddress)
 *     ?? throw new InvalidOperationException("No adapter found on the device subnet.");
 * var localPort = 2000;
 *
 * using (var driver = new ActiveDriverUdp(deviceAddress, 2000, localAddress, 2000))
 * {
 *     driver.Send("?V");
 *     while (true)
 *     {
 *         var responses = driver.GetUdpResponse(0.2);
 *         if (responses.Count == 0 || (responses.Count == 1 && responses[0] == ""))
 *             break;
 *         foreach (string response in responses)
 *             Console.WriteLine(response);
 *     }
 * }
 *
 * GetUdpResponse waits up to the supplied timeout in seconds for each batch.
 * Disposing the driver closes the receiver and stops its listener thread.
 *
 * See active driver communications manual for full list of commands.
 * Common profile commands
 *  +A55  -- set amplitude to 55
 *  +F60.0 or +F60  -- set frequency to 60
 *  +D4  -- set duration [cycles] to 4
 */



using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using System.Threading;


public sealed class ActiveDriverUdp : IDisposable
{
    private readonly UdpClient receiver;
    private readonly IPEndPoint destination;
    private readonly Thread listener;
    private readonly object sync = new object();
    private readonly List<string> messages = new List<string>();
    private bool closed;
    private Exception receiveError;

    public ActiveDriverUdp(IPAddress deviceAddress, int devicePort, IPAddress localAddress, int localPort)
    {
        destination = new IPEndPoint(deviceAddress, devicePort);
        receiver = new UdpClient(AddressFamily.InterNetwork);
        try
        {
            receiver.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
            receiver.Client.Bind(new IPEndPoint(localAddress, localPort));
            listener = new Thread(Receive) { IsBackground = true };
            listener.Start();
            // Send version query as a litmus of active connection
            Send("?v");
            List<string> version = GetUdpResponse(0.5);
            if (version.Count == 0)
                throw new TimeoutException("Timeout - Active Driver did not respond to the version query during initialization.");
        }
        catch (Exception exception)
        {
            lock (sync)
            {
                closed = true;
                Monitor.PulseAll(sync);
            }
            receiver.Close();
            if (listener != null && listener.IsAlive)
                listener.Join();
            throw new InvalidOperationException(
                $"Failed to initialize Active Driver UDP communication with {deviceAddress}:{devicePort} using local endpoint {localAddress}:{localPort}.",
                exception);
        }
    }

    public static IPAddress FindAdapterAddress(IPAddress target)
    {
        // Find the network adaptor that would connect to the provided target (active driver IP)
        // Return null if no match
        byte[] targetBytes = target.GetAddressBytes();
        foreach (NetworkInterface adapter in NetworkInterface.GetAllNetworkInterfaces())
        {
            foreach (UnicastIPAddressInformation address in adapter.GetIPProperties().UnicastAddresses)
            {
                if (address.Address.AddressFamily != AddressFamily.InterNetwork || address.IPv4Mask == null)
                    continue;
                byte[] localBytes = address.Address.GetAddressBytes();
                byte[] mask = address.IPv4Mask.GetAddressBytes();
                bool matches = true;
                for (int i = 0; i < 4; i++)
                    if ((targetBytes[i] & mask[i]) != (localBytes[i] & mask[i]))
                        matches = false;
                if (matches)
                    return address.Address;
            }
        }
        return null;
    }

    private void Receive()
    {
        try
        {
            while (true)
            {
                IPEndPoint sender = new IPEndPoint(IPAddress.Any, 0);
                byte[] data = receiver.Receive(ref sender);
                string message = Encoding.UTF8.GetString(data).TrimEnd('\0');
                lock (sync)
                {
                    if (closed)
                        return;
                    messages.Add(message);
                    Monitor.PulseAll(sync);
                }
            }
        }
        catch (Exception exception)
        {
            lock (sync)
            {
                if (!closed)
                    receiveError = exception;
                closed = true;
                Monitor.PulseAll(sync);
            }
        }
    }

    public void Send(string command)
    {
        lock (sync)
        {
            if (closed)
                throw new InvalidOperationException("UDP receiver is closed", receiveError);
            messages.Clear();
        }
        byte[] data = Encoding.ASCII.GetBytes(command);
        using (var sender = new UdpClient(AddressFamily.InterNetwork))
            sender.Send(data, data.Length, destination);
    }

    public List<string> GetUdpResponse(double timeoutSeconds)
    {
        var elapsed = Stopwatch.StartNew();
        lock (sync)
        {
            while (messages.Count == 0 && !closed)
            {
                double remaining = timeoutSeconds - elapsed.Elapsed.TotalSeconds;
                if (remaining <= 0)
                    return new List<string>();
                int waitMilliseconds = (int)Math.Min(int.MaxValue, Math.Max(1, Math.Ceiling(remaining * 1000)));
                Monitor.Wait(sync, waitMilliseconds);
            }
            if (messages.Count == 0 && closed)
                throw new InvalidOperationException("UDP receiver is closed", receiveError);
            var result = new List<string>(messages);
            messages.Clear();
            return result;
        }
    }

    public void Dispose()
    {
        lock (sync)
        {
            closed = true;
            messages.Clear();
            Monitor.PulseAll(sync);
        }
        receiver.Close();
        listener.Join();
    }
}
