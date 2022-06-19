(defun set-flychecker-executables ()
  "Configure virtualenv for flake8 and lint."
  (when (get-current-buffer-flake8)
    (flycheck-set-checker-executable (quote python-flake8)
                                     (get-current-buffer-flake8)))
  (when (get-current-buffer-pylint)
    (flycheck-set-checker-executable (quote python-pylint)
                                     (get-current-buffer-pylint))))
(add-hook 'flycheck-before-syntax-check-hook
          #'set-flychecker-executables 'local)
