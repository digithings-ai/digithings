export function periodStatusLabel(status: string): string {
  switch (status) {
    case 'final':
      return 'Final';
    case 'estimated':
      return 'Estimated';
    case 'incomplete':
      return 'Incomplete';
    case 'failed':
      return 'Failed';
    default:
      return status;
  }
}
