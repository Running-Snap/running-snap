// app/index.tsx
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
        // 토큰 로드 실패 시에는 로그인 상태로 간주
        setHasToken(false);
      } finally {
        setIsLoading(false);
      }
    };
    init();
  }, []);

  // 토큰 로드 중에는 로딩 스피너만 보여줌
  if (isLoading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator />
      </View>
    );
  }

  // 토큰이 없으면 로그인 화면으로
  if (!hasToken) {
    return <Redirect href="/login" />;
  }

  // 토큰이 있으면 바로 탭(홈)으로
  return <Redirect href="/(tabs)" />;
}