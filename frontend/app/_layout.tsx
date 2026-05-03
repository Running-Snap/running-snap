import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';
import { useEffect } from 'react';

import { useColorScheme } from '@/hooks/use-color-scheme';
import { loadToken } from '@/constants/api';

export default function RootLayout() {
  const colorScheme = useColorScheme();

  useEffect(() => {
    loadToken();
  }, []);

  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <Stack>
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="login" options={{ headerShown: false, gestureEnabled: false }} />
        <Stack.Screen name="register" options={{ headerShown: false }} />
        <Stack.Screen name="analysis-result" options={{ headerShown: false }} />
        <Stack.Screen name="shortform-result" options={{ headerShown: false }} />
        <Stack.Screen name="history" options={{ headerShown: false }} />
        <Stack.Screen name="shortform-list" options={{ headerShown: false }} />
        <Stack.Screen name="best-cut-result" options={{ headerShown: false }} />
        <Stack.Screen name="best-cut-history" options={{ headerShown: false }} />
        <Stack.Screen name="coaching-result" options={{ headerShown: false }} />
        <Stack.Screen name="cert-result" options={{ headerShown: false }} />
        <Stack.Screen name="my-clips" options={{ headerShown: false }} />
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      </Stack>
      <StatusBar style="auto" />
    </ThemeProvider>
  );
}