using UnityEngine;

public class CarDestroyer : MonoBehaviour 
{
    private void OnTriggerEnter(Collider other) 
    {
        if (other.CompareTag("Car")) // Make sure your cars are tagged "Car"
        {
            Destroy(other.gameObject);
        }
    }
}
