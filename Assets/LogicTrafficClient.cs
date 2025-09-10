using System;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;
using Newtonsoft.Json;

[Serializable]
public class LogicCarState
{
    public int car_id;
    public List<float> position;  // [x, y] from Logic Client
    public bool stopped;
    public string lane;
    public int direction;
    public bool turning;
    public float rotation;
}

[Serializable]
public class LogicLightState
{
    public string state;
    public float timer;
    public int vehicles_passed;
}

[Serializable]
public class LogicSensorState
{
    public int value;
    public float x;
    public float y;
}

[Serializable]
public class LogicDebugState
{
    public List<int> sequence;
    public int current_step;
    public float timer;
    public float duration;
    public int sensor_Ah;
    public int sensor_Nog;
    public bool flag_Ah;
    public bool flag_Nog;
    public string current_light;
}

[Serializable]
public class LogicTrafficState
{
    public List<LogicCarState> cars;
    public Dictionary<string, LogicLightState> lights;
    public Dictionary<string, LogicSensorState> sensors;
    public LogicDebugState debug;
}

public class LogicTrafficClient : MonoBehaviour
{
    [Header("Server Settings")]
    public string host = "127.0.0.1";
    public int port = 5555;

    [Header("Prefabs")]
    public GameObject carPrefab;
    public GameObject sensorPrefab;

    [Header("Traffic Lights")]
    public GameObject light0Obj;
    public GameObject light1Obj;
    public GameObject light2Obj;
    public GameObject light3Obj;

    [Header("Debug UI")]
    public UnityEngine.UI.Text debugText;

    private TcpClient client;
    private NetworkStream stream;
    private Thread receiveThread;
    private Dictionary<int, GameObject> carObjects = new Dictionary<int, GameObject>();
    private Dictionary<string, GameObject> lightObjects;
    private Dictionary<string, GameObject> sensorObjects = new Dictionary<string, GameObject>();

    void Start()
    {
        // Setup light dictionary
        lightObjects = new Dictionary<string, GameObject>
        {
            { "light_0", light0Obj },
            { "light_1", light1Obj },
            { "light_2", light2Obj },
            { "light_3", light3Obj }
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
                Debug.Log("Connected to Logic Python server!");

                byte[] buffer = new byte[8192];
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

                        LogicTrafficState state = JsonConvert.DeserializeObject<LogicTrafficState>(messages[i]);
                        UnityMainThreadDispatcher.Instance().Enqueue(() =>
                        {
                            UpdateCars(state);
                            UpdateLights(state);
                            UpdateSensors(state);
                            UpdateDebugUI(state);
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

    void UpdateCars(LogicTrafficState state)
    {
        if (state.cars == null) return;

        HashSet<int> activeCars = new HashSet<int>();

        foreach (var car in state.cars)
        {
            activeCars.Add(car.car_id);

            if (!carObjects.ContainsKey(car.car_id))
            {
                GameObject carObj = Instantiate(carPrefab);
                carObj.name = $"Car_{car.car_id}_{car.lane}";
                carObjects[car.car_id] = carObj;
            }

            GameObject go = carObjects[car.car_id];
            if (go == null)
            {
                carObjects.Remove(car.car_id);
                continue;
            }

            go.transform.position = new Vector3(car.position[0], 0.5f, car.position[2]);
            go.transform.rotation = Quaternion.Euler(0, car.rotation, 0);

            Renderer rend = go.GetComponent<Renderer>();
            if (rend != null)
            {
                System.Random rand = new System.Random(car.car_id);
                Color color = new Color((float)rand.NextDouble(), (float)rand.NextDouble(), (float)rand.NextDouble());
                rend.material.color = color;
            }
        }

        // Remove cars no longer active
        List<int> carsToRemove = new List<int>();
        foreach (var kvp in carObjects)
        {
            if (!activeCars.Contains(kvp.Key))
            {
                carsToRemove.Add(kvp.Key);
                if (kvp.Value != null) Destroy(kvp.Value);
            }
        }
        foreach (int id in carsToRemove) carObjects.Remove(id);
    }

    void UpdateLights(LogicTrafficState state)
    {
        if (state.lights == null) return;

        foreach (var kvp in lightObjects)
        {
            if (kvp.Value == null || !state.lights.ContainsKey(kvp.Key)) continue;

            LogicLightState lightState = state.lights[kvp.Key];
            Renderer rend = kvp.Value.GetComponent<Renderer>();
            if (rend != null)
            {
                switch (lightState.state.ToLower())
                {
                    case "green": rend.material.color = Color.green; break;
                    case "yellow": rend.material.color = Color.yellow; break;
                    default: rend.material.color = Color.red; break;
                }
            }

            Light lightComponent = kvp.Value.GetComponent<Light>();
            if (lightComponent != null)
            {
                lightComponent.color = rend.material.color;
                lightComponent.enabled = lightState.state.ToLower() == "green";
            }
        }
    }

    void UpdateSensors(LogicTrafficState state)
    {
        if (state.sensors == null || sensorPrefab == null) return;

        foreach (var kvp in state.sensors)
        {
            string sensorName = kvp.Key;
            LogicSensorState sensorState = kvp.Value;

            if (!sensorObjects.ContainsKey(sensorName))
            {
                GameObject sensorObj = Instantiate(sensorPrefab);
                sensorObj.name = sensorName;
                sensorObj.transform.position = new Vector3(sensorState.x, 0.1f, sensorState.y);
                sensorObjects[sensorName] = sensorObj;
            }

            GameObject obj = sensorObjects[sensorName];
            if (obj != null)
            {
                Renderer rend = obj.GetComponent<Renderer>();
                if (rend != null)
                {
                    rend.material.color = sensorState.value == 1 ? Color.green : Color.gray;
                }
            }
        }
    }

    void UpdateDebugUI(LogicTrafficState state)
    {
        if (debugText == null || state.debug == null) return;

        StringBuilder sb = new StringBuilder();
        sb.AppendLine($"Current Light: {state.debug.current_light}");
        sb.AppendLine($"Timer: {state.debug.timer:F1}/{state.debug.duration:F1}");
        sb.AppendLine($"Step: {state.debug.current_step}");
        if (state.debug.sequence != null) sb.AppendLine($"Sequence: [{string.Join(", ", state.debug.sequence)}]");
        sb.AppendLine($"Sensor Ah: {state.debug.sensor_Ah} (Flag: {state.debug.flag_Ah})");
        sb.AppendLine($"Sensor Nog: {state.debug.sensor_Nog} (Flag: {state.debug.flag_Nog})");

        if (state.cars != null)
        {
            sb.AppendLine($"Total Cars: {state.cars.Count}");
            Dictionary<string, int> laneCounts = new Dictionary<string, int>();
            foreach (var car in state.cars)
            {
                if (laneCounts.ContainsKey(car.lane)) laneCounts[car.lane]++;
                else laneCounts[car.lane] = 1;
            }
            foreach (var kvp in laneCounts) sb.AppendLine($"{kvp.Key}: {kvp.Value}");
        }

        debugText.text = sb.ToString();
    }

    void OnApplicationQuit()
    {
        try
        {
            if (stream != null) stream.Close();
            if (client != null) client.Close();
            if (receiveThread != null && receiveThread.IsAlive) receiveThread.Abort();
        }
        catch { }
    }
}
