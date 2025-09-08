#include <iostream>
#include <vector>
using namespace std;

int main() {
    int t1Size, t2Size;
    while (cin >> t1Size >> t2Size) {
        if (t1Size == 0 && t2Size == 0) break;

        vector<int> t1(t1Size), t2(t2Size);
        for (int i = 0; i < t1Size; i++) cin >> t1[i];
        for (int i = 0; i < t2Size; i++) cin >> t2[i];

        vector<int> result(t1Size + t2Size);
        for (int i = 0; i < t1Size + t2Size; i++) cin >> result[i];

        // DP table
        vector<vector<bool>> dp(t1Size + 1, vector<bool>(t2Size + 1, false));
        dp[0][0] = true;

        for (int j = 0; j <= t2Size; j++) {
            for (int i = 0; i <= t1Size; i++) {
                if (i < t1Size && t1[i] == result[i + j]) {
                    dp[i+1][j] = dp[i+1][j] || dp[i][j];
                }
                if (j < t2Size && t2[j] == result[i + j]) {
                    dp[i][j+1] = dp[i][j+1] || dp[i][j];
                }
            }
        }

        if (dp[t1Size][t2Size]) {
            cout << "possible" << endl;
        } else {
            cout << "not possible" << endl;
        }
    }
}
//time complexity: O(n*m) where n and m are the sizes of the two input sequences
//space complexity: O(n*m) for the DP table
