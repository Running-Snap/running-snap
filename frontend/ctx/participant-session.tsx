import { createContext, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

type SessionContextType = {
  participantNumber: string | null;
  isLoading: boolean;
  enterWithParticipantNumber: (value: string) => Promise<void>;
  clearParticipantSession: () => Promise<void>;
};

const SessionContext = createContext<SessionContextType | null>(null);

const PARTICIPANT_KEY = 'participant-number';

export function ParticipantSessionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [participantNumber, setParticipantNumber] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 앱 시작 시 저장된 번호 복원
  useEffect(() => {
    const restore = async () => {
      try {
      const saved = await AsyncStorage.getItem(PARTICIPANT_KEY);
      setParticipantNumber(saved || null);
    } catch (e) {
      console.error('SecureStore 복원 실패:', e);
      setParticipantNumber(null);
    } finally {
      setIsLoading(false); // 에러가 나도 반드시 로딩 해제
    }
    };
    restore();
  }, []);

  // 참가자 번호 저장 + 세션 열기
  const enterWithParticipantNumber = async (value: string) => {
    await AsyncStorage.setItem(PARTICIPANT_KEY, value);
    setParticipantNumber(value);
  };

  // 세션 초기화 (로그아웃/퇴장)
  const clearParticipantSession = async () => {
    await AsyncStorage.removeItem(PARTICIPANT_KEY);
    setParticipantNumber(null);
  };

  return (
    <SessionContext.Provider
      value={{
        participantNumber,
        isLoading,
        enterWithParticipantNumber,
        clearParticipantSession,
      }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useParticipantSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useParticipantSession must be used within ParticipantSessionProvider');
  return ctx;
}