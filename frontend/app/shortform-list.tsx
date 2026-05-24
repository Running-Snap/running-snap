import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { apiListCertJobs, CertJob, formatKoreanDateTime } from '@/constants/api';

export default function ShortformListScreen() {
  const [jobs, setJobs] = useState<CertJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    apiListCertJobs()
      .then(data => setJobs(data.filter(j => j.status === 'done')))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={styles.backButton}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>인증영상 기록</Text>
        <Text style={styles.subtitle}>총 {jobs.length}개의 인증영상</Text>
      </View>

      {isLoading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#34C759" />
        </View>
      ) : (
        <ScrollView style={styles.content}>
          {jobs.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyIcon}>🏅</Text>
              <Text style={styles.emptyText}>아직 인증영상이 없어요</Text>
              <Text style={styles.emptySubText}>마라톤 완주 후 인증영상을 받아보세요!</Text>
            </View>
          ) : (
            jobs.map(job => {
              const date = formatKoreanDateTime(job.created_at);
              return (
                <TouchableOpacity
                  key={job.id}
                  style={styles.certCard}
                  onPress={() => router.push({ pathname: '/cert-result', params: { jobId: String(job.id) } })}
                >
                  <View style={styles.thumbnail}>
                    <Text style={styles.thumbnailIcon}>🏅</Text>
                  </View>
                  <View style={styles.certInfo}>
                    <Text style={styles.certDate}>{date}</Text>
                    <Text style={styles.certDetails}>
                      {job.mode === 'full' ? '풀 버전' : '심플 버전'}
                    </Text>
                  </View>
                  <Text style={styles.arrowIcon}>›</Text>
                </TouchableOpacity>
              );
            })
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
  emptySubText: { fontSize: 14, color: '#aaa' },
  certCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16, marginBottom: 12,
    flexDirection: 'row', alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  thumbnail: {
    width: 60, height: 60, backgroundColor: '#1a1a1a', borderRadius: 8,
    alignItems: 'center', justifyContent: 'center', marginRight: 16,
  },
  thumbnailIcon: { fontSize: 24 },
  certInfo: { flex: 1 },
  certDate: { fontSize: 16, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  certDetails: { fontSize: 14, color: '#666' },
  arrowIcon: { fontSize: 24, color: '#ccc' },
});