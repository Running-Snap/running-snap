import { useState } from 'react';
import { View, Text, TextInput, Pressable, Alert, StyleSheet } from 'react-native';
import { router } from 'expo-router';
import { useParticipantSession } from '@/ctx/participant-session';

export default function ParticipantEntryScreen() {
  const [value, setValue] = useState('');
  const { enterWithParticipantNumber } = useParticipantSession();

  const handleChange = (text: string) => {
    setValue(text.replace(/[^0-9]/g, ''));
  };

  const handleEnter = async () => {
    if (!value.trim()) {
      Alert.alert('안내', '참가자 번호를 입력해주세요.');
      return;
    }
    await enterWithParticipantNumber(value);
    router.replace('/(tabs)');
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>참가자 번호 입력</Text>
      <Text style={styles.subtitle}>
        대회 참가자 번호를 입력하면 결과를 조회할 수 있습니다.
      </Text>

      <TextInput
        value={value}
        onChangeText={handleChange}
        keyboardType="numeric"
        placeholder="예: 1234"
        style={styles.input}
      />

      <Pressable onPress={handleEnter} style={styles.button}>
        <Text style={styles.buttonText}>입장하기</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    justifyContent: 'center',
  },
  title: {
    fontSize: 26,
    fontWeight: '700',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 15,
    color: '#666',
    marginBottom: 28,
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 18,
    marginBottom: 16,
  },
  button: {
    backgroundColor: '#111',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});