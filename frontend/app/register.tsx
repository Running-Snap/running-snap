import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator, StyleSheet, Text,
  TextInput, TouchableOpacity, View,
} from 'react-native';
import { apiRegister } from '@/constants/api';

type Status = 'idle' | 'loading' | 'success' | 'error';

export default function RegisterScreen() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  // 성공 시 3초 후 자동으로 로그인 화면 이동
  useEffect(() => {
    if (status !== 'success') return;
    const timer = setTimeout(() => router.back(), 3000);
    return () => clearTimeout(timer);
  }, [status]);

  // 입력값 유효성 검사
  const validate = (): string | null => {
    if (!username || !email || !password || !passwordConfirm)
      return '모든 항목을 입력해주세요.';
    if (password !== passwordConfirm)
      return '비밀번호가 일치하지 않습니다.';
    if (password.length < 4)
      return '비밀번호는 4자 이상이어야 합니다.';
    return null;
  };

  const handleRegister = async () => {
    const validationError = validate();
    if (validationError) {
      setErrorMsg(validationError);
      setStatus('error');
      return;
    }

    setStatus('loading');
    setErrorMsg('');

    try {
      await apiRegister(username, email, password);
      setStatus('success');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '회원가입에 실패했습니다.';
      setErrorMsg(msg);
      setStatus('error');
    }
  };

  // ── 처리 중 화면 ──────────────────────────────────
  if (status === 'loading') {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#007AFF" />
        <Text style={styles.loadingTitle}>계정 생성 중...</Text>
        <Text style={styles.loadingSubtitle}>잠시만 기다려주세요 😊</Text>
      </View>
    );
  }

  // ── 가입 성공 화면 ────────────────────────────────
  if (status === 'success') {
    return (
      <View style={styles.centerContainer}>
        <View style={styles.successIcon}>
          <Text style={styles.successIconText}>✓</Text>
        </View>
        <Text style={styles.successTitle}>가입이 완료되었습니다!</Text>
        <Text style={styles.successSubtitle}>
          잠시 후 로그인 화면으로 이동합니다...
        </Text>
        <TouchableOpacity
          style={styles.goLoginButton}
          onPress={() => router.back()}
        >
          <Text style={styles.goLoginButtonText}>지금 바로 로그인하기</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── 가입 폼 (idle / error) ────────────────────────
  return (
    <View style={styles.container}>
      <Text style={styles.title}>회원가입</Text>
      <Text style={styles.subtitle}>RunningDiary에 오신 것을 환영합니다</Text>

      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          placeholder="아이디 (username)"
          placeholderTextColor="#999"
          autoCapitalize="none"
          value={username}
          onChangeText={(v: string) => { setUsername(v); setStatus('idle'); }}
        />
        <TextInput
          style={styles.input}
          placeholder="이메일"
          placeholderTextColor="#999"
          keyboardType="email-address"
          autoCapitalize="none"
          value={email}
          onChangeText={(v: string) => { setEmail(v); setStatus('idle'); }}
        />
        <TextInput
          style={styles.input}
          placeholder="비밀번호"
          placeholderTextColor="#999"
          secureTextEntry
          value={password}
          onChangeText={(v: string) => { setPassword(v); setStatus('idle'); }}
        />
        <TextInput
          style={styles.input}
          placeholder="비밀번호 확인"
          placeholderTextColor="#999"
          secureTextEntry
          value={passwordConfirm}
          onChangeText={(v: string) => { setPasswordConfirm(v); setStatus('idle'); }}
        />
      </View>

      {/* 실패 메시지 */}
      {status === 'error' && (
        <View style={styles.errorBox}>
          <Text style={styles.errorIcon}>✕</Text>
          <Text style={styles.errorText}>{errorMsg}</Text>
        </View>
      )}

      <TouchableOpacity style={styles.registerButton} onPress={handleRegister}>
        <Text style={styles.registerButtonText}>가입하기</Text>
      </TouchableOpacity>

      <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
        <Text style={styles.backButtonText}>이미 계정이 있으신가요? 로그인</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  // ── 공통 ──
  centerContainer: {
    flex: 1,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
  },

  // ── 처리 중 ──
  loadingTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#000',
    marginTop: 24,
    marginBottom: 8,
  },
  loadingSubtitle: {
    fontSize: 15,
    color: '#666',
  },

  // ── 성공 ──
  successIcon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#34C759',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  successIconText: {
    fontSize: 40,
    color: '#fff',
    fontWeight: 'bold',
  },
  successTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#000',
    marginBottom: 12,
    textAlign: 'center',
  },
  successSubtitle: {
    fontSize: 15,
    color: '#666',
    marginBottom: 32,
    textAlign: 'center',
  },
  goLoginButton: {
    backgroundColor: '#007AFF',
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 32,
  },
  goLoginButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },

  // ── 폼 ──
  container: {
    flex: 1,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#007AFF',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 16,
    color: '#666',
    marginBottom: 40,
  },
  inputContainer: {
    width: '100%',
    marginBottom: 12,
  },
  input: {
    width: '100%',
    height: 50,
    backgroundColor: '#f5f5f5',
    borderRadius: 10,
    paddingHorizontal: 15,
    marginBottom: 15,
    fontSize: 16,
  },

  // ── 에러 박스 ──
  errorBox: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFF0F0',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#FF3B30',
    paddingVertical: 12,
    paddingHorizontal: 16,
    marginBottom: 16,
    gap: 10,
  },
  errorIcon: {
    fontSize: 16,
    color: '#FF3B30',
    fontWeight: 'bold',
  },
  errorText: {
    flex: 1,
    fontSize: 14,
    color: '#FF3B30',
    fontWeight: '600',
  },

  registerButton: {
    width: '100%',
    height: 50,
    backgroundColor: '#007AFF',
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 15,
  },
  registerButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  backButton: {
    marginTop: 10,
  },
  backButtonText: {
    color: '#007AFF',
    fontSize: 14,
  },
});
