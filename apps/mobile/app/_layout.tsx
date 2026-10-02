import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { colors } from "../src/theme";

/**
 * Retries stay at 1: the api layer already distinguishes retryable failures (5xx, timeouts, 409
 * turn_in_progress) from the ones where a retry cannot help (§7.12), and a chat turn is not something to
 * silently send three times.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.background },
            headerTintColor: colors.text,
            headerTitleStyle: { fontWeight: "600" },
            contentStyle: { backgroundColor: colors.background },
          }}
        >
          <Stack.Screen name="index" options={{ title: "Voxora" }} />
          <Stack.Screen name="scenarios/index" options={{ title: "选场景" }} />
          <Stack.Screen name="scenarios/[scenarioId]" options={{ title: "场景" }} />
          <Stack.Screen name="practice/[sessionId]" options={{ title: "练习中" }} />
          <Stack.Screen name="evaluation/[sessionId]" options={{ title: "反馈" }} />
          <Stack.Screen name="review" options={{ title: "复习" }} />
          <Stack.Screen name="review/[id]" options={{ title: "复习项" }} />
          <Stack.Screen name="settings" options={{ title: "设置" }} />
        </Stack>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
