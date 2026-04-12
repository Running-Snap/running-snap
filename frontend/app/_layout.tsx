import { DarkTheme, DefaultTheme, ThemeProvider } from '@react-navigation/native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';
import { useEffect } from 'react';
import { View, ActivityIndicator } from 'react-native';

import { useColorScheme } from '@/hooks/use-color-scheme';
import { loadToken } from '@/constants/api';
import { ParticipantSessionProvider, useParticipantSession } from '@/ctx/participant-session'; 

// GPS 기능 보류 중
// function useGpsTracking() { ... }

function RootNavigator() {
  const { isLoading } = useParticipantSession();

  if (isLoading) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
        <ActivityIndicator />
      </View>
    );
  }



  return (
    <Stack>
      <Stack.Screen name="participant-entry" options={{ headerShown: false }} />
      <Stack.Screen name="login" options={{ headerShown: false, gestureEnabled: false }} />
      <Stack.Screen name="register" options={{ headerShown: false }} />
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="analysis-result" options={{ headerShown: false }} />
      <Stack.Screen name="shortform-result" options={{ headerShown: false }} />
      <Stack.Screen name="history" options={{ headerShown: false }} />
      <Stack.Screen name="shortform-list" options={{ headerShown: false }} />
      <Stack.Screen name="best-cut-result" options={{ headerShown: false }} />
      <Stack.Screen name="best-cut-history" options={{ headerShown: false }} />
      <Stack.Screen name="coaching-result" options={{ headerShown: false }} />
      <Stack.Screen name="my-clips" options={{ headerShown: false }} />
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
    </Stack>
  );
}

export default function RootLayout() {
  const colorScheme = useColorScheme();

  useEffect(() => {
    loadToken();
  }, []);

  return (
    <ParticipantSessionProvider>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <RootNavigator />
        <StatusBar style="auto" />
      </ThemeProvider>
    </ParticipantSessionProvider>
  );
}