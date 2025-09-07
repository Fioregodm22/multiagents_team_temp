using System;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using Newtonsoft.Json;

[Serializable]
public class CarState
{
    public int car_id;
    public List<float> position;
    public bool stopped;
    public float rotation;
    public string direction;
    public int lane;
    public bool turning;
}

[Serializable]
public class LightState
{
    public string state;
    public float timer;
}

[Serializable]
public class TrafficState
{
    public List<CarState> cars;
    public Dictionary<string, LightState> lights;
}

public class TrafficClient : MonoBehaviour
{
    public string host = "127.0.0.1";
    public int port = 5555;
    public GameObject carPrefab;

    // Assign these in the inspector
    public GameObject northLightObj;
    public GameObject southLightObj;
    public GameObject leftLightObj;
    public GameObject rightLightObj;

    private TcpClient client;
    private NetworkStream stream;
    private Thread receiveThread;
    private Dictionary<int, GameObject> carObjects = new Dictionary<int, GameObject>();

    private Dictionary<string, GameObject> lightObjects;

    void Start()
    {
        // Setup light dictionary
        lightObjects = new Dictionary<string, GameObject>
        {
            { "north", northLightObj },
            { "south", southLightObj },
            { "left", leftLightObj },
            { "right", rightLightObj }
        };

        ConnectToServer();
    }

    void ConnectToServer()
    {
        receiveThread = new Thread(() =>
        {
            try
            {
                client = new TcpClient(host, port);
                stream = client.GetStream();
                Debug.Log("Connected to Python server!");

                byte[] buffer = new byte[4096];
                StringBuilder sb = new StringBuilder();

                while (true)
                {
                    int bytesRead = stream.Read(buffer, 0, buffer.Length);
                    if (bytesRead == 0) break;

                    sb.Append(Encoding.UTF8.GetString(buffer, 0, bytesRead));
                    string[] messages = sb.ToString().Split('\n');

                    for (int i = 0; i < messages.Length - 1; i++)
                    {
                        if (string.IsNullOrWhiteSpace(messages[i])) continue;

                        TrafficState state = JsonConvert.DeserializeObject<TrafficState>(messages[i]);
                        UnityMainThreadDispatcher.Instance().Enqueue(() =>
                        {
                            UpdateCars(state);
                            UpdateLights(state);
                        });
                    }

                    sb.Clear();
                    sb.Append(messages[messages.Length - 1]);
                }
            }
            catch (Exception e)
            {
                Debug.LogError("Connection error: " + e);
            }
        });

        receiveThread.IsBackground = true;
        receiveThread.Start();
    }

        void UpdateCars(TrafficState state)
    {
        foreach (var car in state.cars)
        {
            // Check if we already have a GameObject
            if (!carObjects.ContainsKey(car.car_id))
            {
                GameObject carObj = Instantiate(carPrefab);
                carObjects[car.car_id] = carObj;
            }

            GameObject go = carObjects[car.car_id];

            // Check if the object was destroyed
            if (go == null)
            {
                carObjects.Remove(car.car_id);
                continue; // skip this car
            }

            go.transform.position = new Vector3(car.position[0], 0, car.position[1]);
            go.transform.rotation = Quaternion.Euler(0, car.rotation, 0);

            Renderer rend = go.GetComponent<Renderer>();
            if (rend != null)
            {
                rend.material.color = car.stopped ? Color.red : Color.green;
            }
        }
    }


    void UpdateLights(TrafficState state)
    {
        if (state.lights == null) return;

        foreach (var kvp in lightObjects)
        {
            string name = kvp.Key;
            GameObject lightObj = kvp.Value;

            if (lightObj == null) continue;
            if (!state.lights.ContainsKey(name)) continue;

            LightState lightState = state.lights[name];
            Renderer rend = lightObj.GetComponent<Renderer>();
            if (rend != null)
            {
                switch (lightState.state.ToLower())
                {
                    case "green":
                        rend.material.color = Color.green;
                        break;
                    case "yellow":
                        rend.material.color = Color.yellow;
                        break;
                    case "red":
                    default:
                        rend.material.color = Color.red;
                        break;
                }
            }
        }
    }

    void OnApplicationQuit()
    {
        if (stream != null) stream.Close();
        if (client != null) client.Close();
        if (receiveThread != null && receiveThread.IsAlive) receiveThread.Abort();
    }
}
