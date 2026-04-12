import { Redirect } from 'expo-router';
import { View, ActivityIndicator } from 'react-native';
import { useParticipantSession } from '@/ctx/participant-session';

export default function Index() {
  const { participantNumber, isLoading } = useParticipantSession();

  if (isLoading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator />
      </View>
    );
  }

  // 참가자 번호 없으면 입력 화면으로
  if (!participantNumber) {
    return <Redirect href="/participant-entry" />;
  }

  // 있으면 홈으로
  return <Redirect href="/(tabs)" />;
}