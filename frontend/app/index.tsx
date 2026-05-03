import { Redirect } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { loadToken } from '@/constants/api';

export default function Index() {
  const [isLoading, setIsLoading] = useState(true);
  const [hasToken, setHasToken] = useState<boolean | null>(null);

  useEffect(() => {
    const init = async () => {
      try {
        const token = await loadToken();
        setHasToken(!!token);
      } catch (e) {
        setHasToken(false);
      } finally {
        setIsLoading(false);
      }
    };
    init();
  }, []);

  if (isLoading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator />
      </View>
    );
  }

  if (!hasToken) {
    return <Redirect href="/login" />;
  }

  return <Redirect href="/(tabs)" />;
}