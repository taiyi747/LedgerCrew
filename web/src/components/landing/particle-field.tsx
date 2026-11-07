import styles from './landing.module.css';

// Keep the existing page integration; this background contains light only.
export function ParticleField() {
  return <div className={styles.ambientEffects} aria-hidden="true">
    <span className={styles.ambientGlow}/>
  </div>;
}
