import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { apiListAnalysisJobs, AnalysisJob, parseUtcDate } from '@/constants/api';

type ParsedRecord = {
  id: number;
  date: string;
  score: number;
};

export default function HistoryScreen() {
  const [records, setRecords] = useState<ParsedRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    apiListAnalysisJobs()
      .then(jobs => {
        const parsed = jobs
          .filter(j => j.status === 'done' && j.result_json)
          .map(j => {
            const r = JSON.parse(j.result_json!) as { score: number };
            const date = j.created_at
              ? (parseUtcDate(j.created_at)?.toLocaleDateString('ko-KR').replace(/\. /g, '.').replace('.', '') ?? '')
              : '';
            return { id: j.id, date, score: r.score };
          });
        setRecords(parsed);
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const getScoreColor = (score: number) => {
    if (score >= 80) return '#34C759';
    if (score >= 60) return '#FF9500';
    return '#FF3B30';
  };

  const getScoreGrade = (score: number) => {
    if (score >= 80) return '훌륭해요 🏆';
    if (score >= 60) return '괜찮아요 👍';
    return '개선 필요 💪';
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={styles.backButton}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>분석 기록</Text>
        <Text style={styles.subtitle}>총 {records.length}개의 분석 기록</Text>
      </View>

      {isLoading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#007AFF" />
        </View>
      ) : (
        <ScrollView style={styles.content}>
          {records.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyIcon}>📋</Text>
              <Text style={styles.emptyText}>아직 분석 기록이 없어요</Text>
              <Text style={styles.emptySubText}>첫 영상을 분석해보세요!</Text>
              <TouchableOpacity
                style={styles.analyzeButton}
                onPress={() => router.push('/analyze-video')}
              >
                <Text style={styles.analyzeButtonText}>영상 분석하러 가기</Text>
              </TouchableOpacity>
            </View>
          ) : (
            records.map(record => (
              <TouchableOpacity
                key={record.id}
                style={styles.recordCard}
                onPress={() => router.push({ pathname: '/analysis-result', params: { jobId: String(record.id) } })}
              >
                <View style={[styles.scoreBadge, { backgroundColor: getScoreColor(record.score) }]}>
                  <Text style={styles.scoreText}>{record.score}</Text>
                  <Text style={styles.scoreLabel}>점</Text>
                </View>
                <View style={styles.recordInfo}>
                  <Text style={styles.recordDate}>{record.date}</Text>
                  <Text style={[styles.recordGrade, { color: getScoreColor(record.score) }]}>
                    {getScoreGrade(record.score)}
                  </Text>
                </View>
                <Text style={styles.arrowIcon}>›</Text>
              </TouchableOpacity>
            ))
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8f9fa' },
  header: {
    paddingTop: 60, paddingHorizontal: 20, paddingBottom: 20,
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  backButton: { fontSize: 16, color: '#007AFF', marginBottom: 16 },
  title: { fontSize: 28, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  subtitle: { fontSize: 14, color: '#666' },
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  content: { flex: 1, padding: 16 },
  emptyState: { alignItems: 'center', paddingVertical: 60 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyText: { fontSize: 16, fontWeight: 'bold', color: '#666', marginBottom: 4 },
  emptySubText: { fontSize: 14, color: '#aaa', marginBottom: 24 },
  analyzeButton: { backgroundColor: '#007AFF', borderRadius: 12, paddingVertical: 12, paddingHorizontal: 24 },
  analyzeButtonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  recordCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12,
    flexDirection: 'row', alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  scoreBadge: { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center', marginRight: 16 },
  scoreText: { fontSize: 20, fontWeight: 'bold', color: '#fff' },
  scoreLabel: { fontSize: 11, color: '#fff' },
  recordInfo: { flex: 1 },
  recordDate: { fontSize: 16, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  recordGrade: { fontSize: 13, fontWeight: '600' },
  arrowIcon: { fontSize: 24, color: '#ccc' },
});
