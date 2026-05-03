// app/(tabs)/index.tsx
import React, { useEffect, useState } from 'react';
import { router } from 'expo-router';
import {
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  Image,
  FlatList,
  ActivityIndicator,
} from 'react-native';
import {
  apiListAnalysisJobs,
  apiListShortformJobs,
  apiListBestcutJobs,
  AnalysisJob,
  ShortformJob,
  BestcutJob,
  formatKoreanTime,
  API_BASE,
} from '@/constants/api';

// 홈 상단 하이라이트 카드에서 사용할 컨텐츠 타입
type HighlightType = 'BEST_CUT' | 'SHORTFORM' | 'ANALYSIS';

interface HomeHighlightItem {
  id: string;              // job id를 문자열로
  type: HighlightType;
  thumbnailUrl: string;    // 현재는 임시 이미지, 나중에 실제 URL로 교체
  title: string;
  createdAt: string;       // 화면에 바로 쓸 포맷된 날짜
}

// 타입별 라벨/색상
const HIGHLIGHT_TYPE_LABEL: Record<HighlightType, string> = {
  BEST_CUT: '베스트 컷',
  SHORTFORM: '숏폼',
  ANALYSIS: '자세 피드백',
};

const HIGHLIGHT_TYPE_COLOR: Record<HighlightType, string> = {
  BEST_CUT: '#FF9500',
  SHORTFORM: '#FF3B30',
  ANALYSIS: '#007AFF',
};

export default function HomeScreen() {
  const [highlightItems, setHighlightItems] = useState<HomeHighlightItem[]>([]);
  const [isLoadingHighlights, setIsLoadingHighlights] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // 서버에서 최근 컨텐츠 하이라이트 불러오기
  useEffect(() => {
    const loadHighlights = async () => {
      try {
        setLoadError(null);
        // 세 종류 기록을 동시에 요청
        const [analysisJobs, shortformJobs, bestcutJobs] = await Promise.all([
          apiListAnalysisJobs(),
          apiListShortformJobs(),
          apiListBestcutJobs(),
        ]);

        // 1) status === 'done'만 필터링
        const doneAnalysis = analysisJobs.filter((j) => j.status === 'done');
        const doneShortforms = shortformJobs.filter((j) => j.status === 'done');
        const doneBestcuts = bestcutJobs.filter((j) => j.status === 'done');

        // 2) 각각을 HomeHighlightItem으로 매핑
        const analysisItems: HomeHighlightItem[] = doneAnalysis.map(
          (job: AnalysisJob): HomeHighlightItem => ({
            id: `analysis-${job.id}`,
            type: 'ANALYSIS',
            thumbnailUrl:
              'https://via.placeholder.com/300x180.png?text=Analysis', // TODO: 실제 썸네일 URL로 교체
            title: '자세 분석 결과',
            createdAt: formatKoreanTime(job.created_at),
          }),
        );

        const shortformItems: HomeHighlightItem[] = doneShortforms.map(
          (job: ShortformJob): HomeHighlightItem => ({
            id: `shortform-${job.id}`,
            type: 'SHORTFORM',
            thumbnailUrl:
              'https://via.placeholder.com/300x180.png?text=Shortform',
            title: job.style
              ? `숏폼 (${job.style})`
              : '숏폼 하이라이트',
            createdAt: formatKoreanTime(job.created_at),
          }),
        );

        const bestcutItems: HomeHighlightItem[] = doneBestcuts.map(
          (job: BestcutJob): HomeHighlightItem => {
            let thumbnailUrl = '';
            try {
              if (job.result_json) {
                const cuts = JSON.parse(job.result_json) as { photo_url: string | null }[];
                const first = cuts.find(c => c.photo_url);
                if (first?.photo_url) {
                  thumbnailUrl = first.photo_url.startsWith('http')
                    ? first.photo_url
                    : `${API_BASE}${first.photo_url}`;
                }
              }
            } catch {}
            return {
              id: `bestcut-${job.id}`,
              type: 'BEST_CUT',
              thumbnailUrl,
              title: '베스트 컷 결과',
              createdAt: formatKoreanTime(job.created_at),
            };
          },
        );

        // 3) 하나의 배열로 합치고, 최신 순으로 정렬
        const merged = [
          ...analysisItems,
          ...shortformItems,
          ...bestcutItems,
        ].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));

        // 4) 너무 많으면 상위 N개만 (예: 10개)
        setHighlightItems(merged.slice(0, 10));
      } catch (e: unknown) {
        const msg =
          e instanceof Error ? e.message : '하이라이트를 불러오지 못했습니다.';
        setLoadError(msg);
      } finally {
        setIsLoadingHighlights(false);
      }
    };

    loadHighlights();
  }, []);

  // 하이라이트 카드 탭 시 상세 화면으로 이동하는 핸들러
  const handlePressHighlight = (item: HomeHighlightItem) => {
    // TODO: 추후 type별로 다른 상세 화면으로 route 분기
    // 예시:
    // if (item.type === 'BEST_CUT') router.push(`/best-cut-result?id=${item.id}`);
    // 지금은 일단 베스트컷 히스토리로 이동
    if (item.type === 'BEST_CUT') {
      const jobId = item.id.replace('bestcut-', '');
      router.push(`/best-cut-result?jobId=${jobId}`);
    } else if (item.type === 'SHORTFORM') {
      const jobId = item.id.replace('shortform-', '');
      router.push(`/shortform-result?jobId=${jobId}`);
    } else {
      const jobId = item.id.replace('analysis-', '');
      router.push(`/analysis-result?jobId=${jobId}`);
    }
  };

  // 상단 캐러셀 카드 UI
  const renderHighlightItem = ({ item }: { item: HomeHighlightItem }) => (
    <TouchableOpacity
      style={styles.highlightCard}
      activeOpacity={0.9}
      onPress={() => handlePressHighlight(item)}
    >
      <Image
        source={{ uri: item.thumbnailUrl }}
        style={styles.highlightThumbnail}
        resizeMode="cover"
      />
      <View style={styles.highlightInfoRow}>
        <View
          style={[
            styles.highlightBadge,
            { backgroundColor: HIGHLIGHT_TYPE_COLOR[item.type] + '20' },
          ]}
        >
          <Text
            style={[
              styles.highlightBadgeText,
              { color: HIGHLIGHT_TYPE_COLOR[item.type] },
            ]}
          >
            {HIGHLIGHT_TYPE_LABEL[item.type]}
          </Text>
        </View>
        <Text style={styles.highlightDate}>{item.createdAt}</Text>
      </View>
      <Text style={styles.highlightTitle} numberOfLines={1}>
        {item.title}
      </Text>
    </TouchableOpacity>
  );

  return (
    <ScrollView style={styles.container}>
      {/* 헤더 */}
      <View style={styles.header}>
        <Text style={styles.welcomeText}>나만의 러닝 하이라이트</Text>
        <Text style={styles.subtitle}>
          이미 생성된 베스트 컷과 숏폼, 자세 피드백을 모아봤어요
        </Text>
      </View>

      {/* 상단 하이라이트 캐러셀 */}
      <View style={styles.highlightSection}>
        {isLoadingHighlights ? (
          <View style={styles.highlightLoadingBox}>
            <ActivityIndicator size="small" color="#007AFF" />
            <Text style={styles.highlightLoadingText}>하이라이트 불러오는 중...</Text>
          </View>
        ) : loadError ? (
          <View style={styles.highlightLoadingBox}>
            <Text style={styles.highlightErrorText}>{loadError}</Text>
          </View>
        ) : highlightItems.length === 0 ? (
          <View style={styles.highlightLoadingBox}>
            <Text style={styles.highlightLoadingText}>
              아직 생성된 컨텐츠가 없어요. 아래에서 먼저 만들어볼까요?
            </Text>
          </View>
        ) : (
          <FlatList
            data={highlightItems}
            keyExtractor={(item) => item.id}
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.highlightListContent}
            renderItem={renderHighlightItem}
          />
        )}
      </View>

      {/* 새 컨텐츠 만들기 섹션 */}
      <View style={styles.mainButtonsSection}>
        <Text style={styles.sectionTitle}>새 컨텐츠 만들기</Text>

        <View style={styles.mainButtons}>
          <TouchableOpacity
            style={[styles.mainButton, styles.analyzeButton]}
            onPress={() => router.push('/analyze-video')}
          >
            <Text style={styles.mainButtonIcon}>🎥</Text>
            <Text style={styles.mainButtonTitle}>영상 분석하기</Text>
            <Text style={styles.mainButtonSubtitle}>AI가 자세를 분석해드려요</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.mainButton, styles.shortformButton]}
            onPress={() => router.push('/create-shortform')}
          >
            <Text style={styles.mainButtonIcon}>✨</Text>
            <Text style={styles.mainButtonTitle}>숏폼 만들기</Text>
            <Text style={styles.mainButtonSubtitle}>여러 영상을 하나로 편집</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.mainButton, styles.bestCutButton]}
            onPress={() => router.push('/best-cut')}
          >
            <Text style={styles.mainButtonIcon}>📸</Text>
            <Text style={styles.mainButtonTitle}>베스트 컷 추출</Text>
            <Text style={styles.mainButtonSubtitle}>
              AI가 최고의 순간을 찾아드려요
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* 기록 섹션 */}
      <View style={styles.section}>
        {/* 최근 분석 기록 */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>최근 분석 기록</Text>
          <TouchableOpacity onPress={() => router.push('/history')}>
            <Text style={styles.seeAllButton}>전체 보기 ›</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.recordPreviewCard}
          onPress={() => router.push('/history')}
        >
          <Text style={styles.emptyStateText}>📋 분석 기록 보러가기</Text>
          <Text style={styles.arrowIcon}>›</Text>
        </TouchableOpacity>

        {/* 숏폼 기록 */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>내 숏폼</Text>
          <TouchableOpacity onPress={() => router.push('/shortform-list')}>
            <Text style={styles.seeAllButton}>전체 보기 ›</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.recordPreviewCard}
          onPress={() => router.push('/shortform-list')}
        >
          <Text style={styles.emptyStateText}>🎬 숏폼 기록 보러가기</Text>
          <Text style={styles.arrowIcon}>›</Text>
        </TouchableOpacity>

        {/* 베스트 컷 기록 */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>내 베스트 컷</Text>
          <TouchableOpacity onPress={() => router.push('/best-cut-history')}>
            <Text style={styles.seeAllButton}>전체 보기 ›</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.recordPreviewCard}
          onPress={() => router.push('/best-cut-history')}
        >
          <Text style={styles.emptyStateText}>📸 베스트 컷 보러가기</Text>
          <Text style={styles.arrowIcon}>›</Text>
        </TouchableOpacity>

        {/* 내 영상 */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>내 영상</Text>
          <TouchableOpacity onPress={() => router.push('/my-clips')}>
            <Text style={styles.seeAllButton}>전체 보기 ›</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.recordPreviewCard}
          onPress={() => router.push('/my-clips')}
        >
          <Text style={styles.emptyStateText}>🎬 카메라가 찍은 내 영상</Text>
          <Text style={styles.arrowIcon}>›</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8f9fa',
  },
  header: {
    padding: 24,
    paddingTop: 60,
    backgroundColor: '#fff',
  },
  welcomeText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#000',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#666',
  },
  highlightSection: {
    paddingVertical: 16,
  },
  highlightListContent: {
    paddingHorizontal: 16,
  },
  highlightLoadingBox: {
    paddingHorizontal: 16,
    paddingVertical: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  highlightLoadingText: {
    marginTop: 8,
    fontSize: 13,
    color: '#666',
    textAlign: 'center',
  },
  highlightErrorText: {
    fontSize: 13,
    color: '#FF3B30',
    textAlign: 'center',
  },
  highlightCard: {
    width: 260,
    marginRight: 16,
    backgroundColor: '#fff',
    borderRadius: 16,
    overflow: 'hidden',
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
  },
  highlightThumbnail: {
    width: '100%',
    height: 140,
  },
  highlightInfoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingTop: 8,
  },
  highlightBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
  },
  highlightBadgeText: {
    fontSize: 12,
    fontWeight: '600',
  },
  highlightDate: {
    fontSize: 11,
    color: '#999',
  },
  highlightTitle: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 14,
    fontWeight: 'bold',
    color: '#000',
  },
  mainButtonsSection: {
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  mainButtons: {
    marginTop: 8,
    gap: 16,
  },
  mainButton: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  analyzeButton: {
    borderLeftWidth: 4,
    borderLeftColor: '#007AFF',
  },
  shortformButton: {
    borderLeftWidth: 4,
    borderLeftColor: '#FF3B30',
  },
  bestCutButton: {
    borderLeftWidth: 4,
    borderLeftColor: '#FF9500',
  },
  mainButtonIcon: {
    fontSize: 40,
    marginBottom: 8,
  },
  mainButtonTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#000',
    marginBottom: 4,
  },
  mainButtonSubtitle: {
    fontSize: 13,
    color: '#666',
  },
  section: {
    padding: 16,
    marginTop: 8,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#000',
  },
  seeAllButton: {
    fontSize: 14,
    color: '#007AFF',
    fontWeight: '600',
  },
  recordPreviewCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    marginBottom: 24,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  emptyStateText: {
    fontSize: 15,
    color: '#666',
  },
  arrowIcon: {
    fontSize: 20,
    color: '#ccc',
  },
});
