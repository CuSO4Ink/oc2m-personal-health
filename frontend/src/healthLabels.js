import { t } from './i18n'
export const metricLabels = {get blood_pressure() { return t("血压") }, get blood_glucose() { return t("血糖") }, get heart_rate() { return t("心率") }}
export const sectionLabels = {get past_history() { return t("既往病史") }, get family_history() { return t("家族病史") }, get medications() { return t("用药情况") }, get allergies() { return t("过敏情况") }}
export const recordLabels = {get 'Lab Report'() { return t("检验报告") }, get 'Visit Summary'() { return t("就诊病历") }, get 'Medication'() { return t("处方与用药") }, get 'Allergy'() { return t("过敏记录") }, get 'Imaging'() { return t("影像报告") }, get 'Other'() { return t("其他资料") }}
export const contextLabels = {get fasting() { return t("空腹") }, get after_meal() { return t("餐后") }, get random() { return t("随机") }, get resting() { return t("静息") }, get exercise() { return t("运动后") }, get unknown() { return t("未确认场景") }}
