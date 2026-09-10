import { useEffect, useRef } from "react";

/** Guards async state updates after unmount (INV-003). */
export function useMountedRef(): { readonly current: boolean } {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return mounted;
}

export function setStateIfMounted<T>(
  mounted: { readonly current: boolean },
  setter: (value: T | ((prev: T) => T)) => void,
  value: T | ((prev: T) => T),
): void {
  if (mounted.current) {
    setter(value);
  }
}
