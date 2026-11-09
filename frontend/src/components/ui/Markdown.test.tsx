import { render, screen } from '@testing-library/react';
import { Markdown } from './Markdown';

it('renders readable Markdown but excludes raw HTML and external images', () => {
  const { container } = render(
    <Markdown>
      {'**Nội dung**\n\n<script>alert(1)</script>\n\n![tracking](https://example.com/track.png)'}
    </Markdown>,
  );
  expect(screen.getByText('Nội dung').tagName).toBe('STRONG');
  expect(container.querySelector('script')).toBeNull();
  expect(container.querySelector('img')).toBeNull();
});

it('allows explicit HTTP links and rejects executable links', () => {
  render(
    <Markdown>{'[Nguồn](https://example.com/source) và [Sai](javascript:alert%281%29)'}</Markdown>,
  );
  expect(screen.getByRole('link', { name: 'Nguồn' })).toHaveAttribute('rel', 'noopener noreferrer');
  expect(screen.queryByRole('link', { name: 'Sai' })).not.toBeInTheDocument();
});
