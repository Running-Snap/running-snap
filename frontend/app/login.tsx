import { router } from 'expo-router';
import { useState } from 'react';
import {
  StyleSheet, Text, TextInput,
  TouchableOpacity, View, KeyboardAvoidingView, Platform,
} from 'react-native';
import { apiLoginWithBib, setToken } from '@/constants/api';

export default function LoginScreen() {
  const [bibNumber, setBibNumber] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleLogin = async () => {
    setErrorMsg('');

    if (!bibNumber.trim()) {
      setErrorMsg('배번호를 입력해주세요.');
      return;
    }

    if (!/^\d+$/.test(bibNumber.trim())) {
      setErrorMsg('배번호는 숫자만 입력해주세요.');
      return;
    }

    setIsLoading(true);
    try {
      const token = await apiLoginWithBib(bibNumber.trim());
      await setToken(token);
      router.replace('/(tabs)');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '로그인 실패';
      setErrorMsg(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.inner}>
        {/* 타이틀 */}
        <Text style={styles.title}>🏃 RunningSnap</Text>
        <Text style={styles.subtitle}>마라톤 대회 하이라이트</Text>

        {/* 안내 문구 */}
        <View style={styles.guideBox}>
          <Text style={styles.guideText}>대회 참가 시 부여받은</Text>
          <Text style={styles.guideTextBold}>배번호를 입력하세요</Text>
        </View>

        {/* 배번호 입력 */}
        <TextInput
          style={[styles.input, errorMsg ? styles.inputError : null]}
          placeholder="배번호 (예: 1042)"
          placeholderTextColor="#999"
          keyboardType="number-pad"   // 숫자 키패드
          value={bibNumber}
          onChangeText={(v) => { setBibNumber(v); setErrorMsg(''); }}
          maxLength={6}               // 배번호 최대 6자리 제한
          returnKeyType="done"
          onSubmitEditing={handleLogin}
        />

        {/* 에러 메시지 */}
        {errorMsg ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{errorMsg}</Text>
          </View>
        ) : null}

        {/* 로그인 버튼 */}
        <TouchableOpacity
          style={[styles.loginButton, isLoading && styles.loginButtonDisabled]}
          onPress={handleLogin}
          disabled={isLoading}
        >
          <Text style={styles.loginButtonText}>
            {isLoading ? '확인 중...' : '입장하기'}
          </Text>
        </TouchableOpacity>

        <Text style={styles.footerText}>
          배번호를 모르시면 대회 운영진에게 문의해주세요
        </Text>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  inner: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#007AFF',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 15,
    color: '#666',
    marginBottom: 48,
  },
  guideBox: {
    alignItems: 'center',
    marginBottom: 24,
  },
  guideText: {
    fontSize: 16,
    color: '#444',
    lineHeight: 24,
  },
  guideTextBold: {
    fontSize: 18,
    fontWeight: '700',
    color: '#222',
    lineHeight: 28,
  },
  input: {
    width: '100%',
    height: 56,
    backgroundColor: '#f5f5f5',
    borderRadius: 12,
    paddingHorizontal: 20,
    fontSize: 24,           // 배번호는 크게
    fontWeight: '700',
    textAlign: 'center',
    letterSpacing: 4,       // 숫자 간격 띄워서 읽기 편하게
    marginBottom: 16,
  },
  inputError: {
    borderWidth: 1.5,
    borderColor: '#FF3B30',
    backgroundColor: '#FFF5F5',
  },
  errorBox: {
    width: '100%',
    backgroundColor: '#FFF5F5',
    borderWidth: 1,
    borderColor: '#FF3B30',
    borderRadius: 10,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    color: '#FF3B30',
    fontSize: 14,
    textAlign: 'center',
    fontWeight: '600',
  },
  loginButton: {
    width: '100%',
    height: 54,
    backgroundColor: '#007AFF',
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
    shadowColor: '#007AFF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  loginButtonDisabled: {
    backgroundColor: '#aaa',
    shadowOpacity: 0,
    elevation: 0,
  },
  loginButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  footerText: {
    fontSize: 12,
    color: '#aaa',
    textAlign: 'center',
    lineHeight: 18,
  },
});