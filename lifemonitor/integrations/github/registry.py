# Copyright (c) 2020-2026 CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import logging
from typing import List, Optional

from lifemonitor.api.models.workflows import Workflow, WorkflowVersion
from lifemonitor.auth.models import User
from lifemonitor.db import db
from lifemonitor.models import ModelMixin

# Set the module level logger
logger = logging.getLogger(__name__)


class GithubWorkflowVersion(db.Model, ModelMixin):
    id = db.Column(db.Integer, primary_key=True)
    registry_id = db.Column(db.ForeignKey("github_workflow_registry.id"), nullable=False)
    workflow_version_id = db.Column(db.ForeignKey('workflow_version.id'), nullable=False)
    repo_identifier = db.Column(db.String, nullable=False)
    repo_ref = db.Column(db.String, nullable=True)
    notifications_enabled = db.Column(db.Boolean, nullable=True, default=True)
    workflow_version: WorkflowVersion = db.relationship(
        "WorkflowVersion", uselist=False,
        backref=db.backref("github_versions", cascade="all, delete-orphan"))

    registry: GithubWorkflowRegistry = db.relationship("GithubWorkflowRegistry", uselist=False,
                                                       back_populates="_workflow_versions")

    __table_args__ = (
        db.UniqueConstraint('registry_id', 'repo_identifier', 'workflow_version_id'),
    )

    def __init__(self, registry: GithubWorkflowRegistry,
                 version: WorkflowVersion, repo: str, ref: str = None) -> None:
        super().__init__()
        self.registry = registry
        self.workflow_version = version
        self.repo_identifier = repo
        self.repo_ref = ref
        self.notifications_enabled = True


class GithubWorkflowRegistry(db.Model, ModelMixin):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, nullable=False)
    installation_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)

    user: User = db.relationship("User", uselist=False, backref=db.backref("github_workflows"))
    _workflow_versions: List[GithubWorkflowVersion] = db.relationship(
        "GithubWorkflowVersion", back_populates="registry")

    __table_args__ = (
        db.UniqueConstraint('application_id', 'installation_id', 'user_id'),
    )

    def __init__(self, user: User, application_id: str, installation_id: str) -> None:
        super().__init__()
        self.application_id = application_id
        self.installation_id = installation_id
        self.user = user

    @property
    def workflows(self) -> List[Workflow]:
        return list({_.workflow for _ in self.workflow_versions})

    @property
    def workflow_versions(self) -> List[GithubWorkflowVersion]:
        return self._workflow_versions

    def add_workflow_version(self, v: WorkflowVersion, repo: str, ref: str) -> GithubWorkflowVersion:
        version = self.get_workflow_version(v)
        if not version:
            return GithubWorkflowVersion(self, v, repo, ref)
        version.repo_ref = ref
        if version.notifications_enabled is None:
            version.notifications_enabled = True
        return version

    def find_workflow_version_by_repo(self, repo: str, ref: Optional[str] = None) -> Optional[GithubWorkflowVersion]:
        return next((w for w in self.workflow_versions
                     if w.repo_identifier == repo and (ref is None or w.repo_ref == ref)), None)

    def remove_workflow_version(self, v: GithubWorkflowVersion):
        if v and v in self._workflow_versions:
            self._workflow_versions.remove(v)

    def contains(self, v: WorkflowVersion) -> bool:
        return v and v in [_.workflow_version for _ in self._workflow_versions]

    def get_workflow_version(self, v: WorkflowVersion) -> GithubWorkflowVersion:
        return next((_ for _ in self.workflow_versions if _.workflow_version == v), None)

    def find_workflow(self, repo: str) -> Workflow:
        logger.debug("Searning repository: %r", repo)
        return next((w.workflow_version.workflow for w in self.workflow_versions if w.repo_identifier == repo), None)

    @classmethod
    def find(cls, user: User, application_id: str, installation_id: str) -> GithubWorkflowRegistry:
        try:
            return cls.query\
                .filter(cls.user_id == user.id)\
                .filter(cls.application_id == application_id)\
                .filter(cls.installation_id == installation_id).one()
        except Exception as e:
            logger.debug(e)
            return None

    @classmethod
    def find_by_id(cls, id: int) -> GithubWorkflowRegistry:
        try:
            return cls.query.filter(cls.useid == id).one()
        except Exception as e:
            logger.debug(e)
            return None
    @classmethod
    def cleanup_registries(cls, installation_ids: List[str], safe: bool = True) -> int:
        """"
        Remove all the workflow versions and registries with missing installation or workflow version.

        :param installation_ids: The list of valid installation ids.
            All the registries with installation id not in this list will be removed.
        :return: The number of removed registries.
        """

        removed = 0

        try:
            registries = cls.all()
            logger.debug("Found %d github workflow registries", len(registries))

            for registry in registries:
                has_missing_installation = registry.installation_id not in installation_ids
                has_missing_workflow_version = any(
                    db.session.get(WorkflowVersion, version.workflow_version_id) is None
                    for version in registry.workflow_versions
                )

                if has_missing_installation or has_missing_workflow_version:
                    reason = "missing installation" if has_missing_installation else "missing workflow version"
                    logger.warning(
                        "Removing github workflow registry %r (installation=%r): %s",
                        registry.id,
                        registry.installation_id,
                        reason,
                    )
                    for version in list(registry.workflow_versions):
                        version.delete(commit=False, flush=False)
                    registry.delete(commit=False, flush=False)
                    removed += 1

            if removed:
                db.session.commit()
                db.session.flush()
            logger.info("Removed %d github workflow registries", removed)
            return removed
        except Exception as e:
            logger.error(e)
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)
            db.session.rollback()
            if not safe:
                raise e
            return 0
